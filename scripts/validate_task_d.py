"""离线校验任务 D 的病例登记、矩阵和脱敏证据。

这个脚本只读取仓库内的 JSON/Markdown，不启动服务、不联网、不读取密钥，
也不把媒体草案或前端状态当成已通过。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data/public_cases/registry.json"
BASELINE = ROOT / "docs/evidence/text-baseline-2026-09-12.json"
RESTART = ROOT / "docs/evidence/process-restart-2026-09-12.json"
MATRIX = ROOT / "docs/qa/test-matrix.md"
COVERAGE = ROOT / "docs/qa/coverage.md"

MATRIX_ID_RE = re.compile(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+")
MATRIX_ROW_RE = re.compile(r"^\s*`?([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)`?\s*$")
KNOWN_SUCCESS_STATUSES = {"passed", "pass", "success", "succeeded"}
KNOWN_FAILURE_STATUSES = {"failed", "failure", "error", "blocked"}
UNIMPLEMENTED_MATRIX_PREFIXES = ("MEDIA-", "UI-", "MOBILE-", "RELEASE-")


def load_json(path: Path, errors: list[str]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{relative_path(path)}: JSON 读取失败: {exc}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{relative_path(path)}: 顶层必须是对象")
        return {}
    return value


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def relative_path(path: Path) -> str:
    """Return a stable repository-relative path for user-facing diagnostics."""

    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def split_markdown_row(line: str) -> list[str]:
    """Split a simple Markdown table row into trimmed cells.

    The QA matrix does not use escaped pipes in cells.  Keeping this parser
    deliberately small makes it clear that IDs come from the first column of
    actual matrix rows, rather than from every inline code span in the file.
    """

    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def parse_matrix_rows(matrix_text: str, errors: list[str]) -> dict[str, dict[str, Any]]:
    """Parse test-case IDs from the matrix's first column.

    The matrix is the source of truth for which IDs exist.  In particular, do
    not maintain a second hand-written list in this validator: adding a row to
    the matrix should automatically make that ID available to case references.
    """

    rows: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(matrix_text.splitlines(), 1):
        if not line.lstrip().startswith("|"):
            continue
        cells = split_markdown_row(line)
        if not cells:
            continue
        first_cell = cells[0]
        if first_cell in {"用例 ID", "测试用例 ID", "ID", "---", ""}:
            continue
        match = MATRIX_ROW_RE.fullmatch(first_cell)
        if not match:
            # A backtick-wrapped first cell is intended to be an ID.  Report a
            # precise error instead of silently dropping a malformed row.
            if first_cell.startswith("`") or first_cell.endswith("`"):
                errors.append(
                    f"{relative_path(MATRIX)}:{line_number}: 第一列不是有效用例 ID: {first_cell!r}"
                )
            continue
        row_id = match.group(1)
        if row_id in rows:
            errors.append(
                f"{relative_path(MATRIX)}:{line_number}: 用例 ID 重复: {row_id}"
            )
            continue
        rows[row_id] = {"line": line_number, "cells": cells, "text": line.strip()}
    require(bool(rows), f"{relative_path(MATRIX)} 未解析到任何测试矩阵行", errors)
    return rows


def resolve_local_ref(document: dict[str, Any], reference: Any) -> Any:
    """Resolve the small JSON-pointer subset used by the case registry."""

    if not isinstance(reference, str) or not reference.startswith("#/"):
        return None
    value: Any = document
    for token in reference[2:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if not isinstance(value, dict) or token not in value:
            return None
        value = value[token]
    return value


def validate_declared_hashes(
    container: dict[str, Any], context: str, errors: list[str]
) -> dict[str, str]:
    """Verify every repository-relative hash explicitly declared by evidence."""

    hashes = container.get("dataset_sha256")
    if hashes is None:
        return {}
    if not isinstance(hashes, dict):
        errors.append(f"{context}.dataset_sha256 必须是对象")
        return {}
    checked: dict[str, str] = {}
    for relative_name, expected in hashes.items():
        item_context = f"{context}.dataset_sha256[{relative_name!r}]"
        if not isinstance(relative_name, str) or not relative_name:
            errors.append(f"{item_context}: 路径必须是非空字符串")
            continue
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
            errors.append(f"{item_context}: 必须是 64 位 SHA-256 十六进制值")
            continue
        target = (ROOT / relative_name).resolve()
        try:
            target.relative_to(ROOT)
        except ValueError:
            errors.append(f"{item_context}: 路径不得指向仓库外部: {relative_name}")
            continue
        if not target.is_file():
            errors.append(f"{item_context}: 文件不存在: {relative_name}")
            continue
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual.lower() != expected.lower():
            errors.append(
                f"{item_context}: SHA-256 不匹配，声明 {expected}，实际 {actual}"
            )
            continue
        checked[relative_name] = actual
    return checked


def validate_evidence_runs(
    evidence: dict[str, Any], context: str, errors: list[str], warnings: list[str]
) -> None:
    """Check declared run fields without assuming a particular machine state.

    A historical evidence file may legitimately say that one environment was
    blocked and another passed.  The validator therefore checks field types
    and obvious result contradictions (for example, ``passed`` with a
    non-zero exit code), rather than requiring those historical labels.
    """

    status = evidence.get("status")
    if not isinstance(status, str) or not status.strip():
        errors.append(f"{context}.status 必须是非空字符串")
    environment = evidence.get("environment")
    if not isinstance(environment, dict):
        errors.append(f"{context}.environment 必须是对象，用于声明运行环境")
    else:
        for key in ("credentials_read", "private_medical_data"):
            if key in environment and not isinstance(environment[key], bool):
                errors.append(f"{context}.environment.{key} 必须是布尔值")
            if environment.get(key) is True:
                errors.append(f"{context}.environment.{key} 不得为 true")
        validate_declared_hashes(environment, f"{context}.environment", errors)

    runs = evidence.get("command_runs")
    if runs is None:
        return
    if not isinstance(runs, list) or not runs:
        errors.append(f"{context}.command_runs 必须是非空数组")
        return
    for index, run in enumerate(runs, 1):
        run_context = f"{context}.command_runs[{index}]"
        if not isinstance(run, dict):
            errors.append(f"{run_context} 必须是对象")
            continue
        for key in ("command", "environment", "status", "summary"):
            if key not in run:
                errors.append(f"{run_context} 缺少 {key}")
        for key in ("command", "environment", "status"):
            if key in run and (not isinstance(run[key], str) or not run[key].strip()):
                errors.append(f"{run_context}.{key} 必须是非空字符串")
        exit_code = run.get("exit_code")
        if exit_code is not None and (
            not isinstance(exit_code, int) or isinstance(exit_code, bool)
        ):
            errors.append(f"{run_context}.exit_code 必须是整数或 null")
        run_status = run.get("status", "").strip().lower() if isinstance(run.get("status"), str) else ""
        if run_status in KNOWN_SUCCESS_STATUSES and exit_code != 0:
            errors.append(
                f"{run_context}: status={run.get('status')!r} 时 exit_code 必须为 0，实际为 {exit_code!r}"
            )
        elif run_status in KNOWN_FAILURE_STATUSES and exit_code == 0:
            warnings.append(
                f"{run_context}: status={run.get('status')!r} 但 exit_code=0，请确认阻塞/失败说明"
            )


def validate_case_references(
    case: dict[str, Any],
    case_context: str,
    matrix_rows: dict[str, dict[str, Any]],
    errors: list[str],
) -> set[str]:
    """Ensure every CASE/TEXT ID actually referenced by a case exists."""

    references = case.get("test_case_ids")
    if not isinstance(references, list) or not references:
        return set()
    seen: set[str] = set()
    for reference in references:
        if not isinstance(reference, str) or not MATRIX_ID_RE.fullmatch(reference):
            errors.append(f"{case_context}.test_case_ids 含无效用例 ID: {reference!r}")
            continue
        if reference in seen:
            errors.append(f"{case_context}.test_case_ids 重复引用: {reference}")
            continue
        seen.add(reference)
        if not reference.startswith(("CASE-", "TEXT-")):
            errors.append(
                f"{case_context}.test_case_ids 只能引用 CASE-/TEXT- 用例，实际为 {reference}"
            )
        if reference not in matrix_rows:
            errors.append(
                f"{case_context}.test_case_ids 引用的矩阵用例不存在: {reference}"
            )
    return seen


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    registry = load_json(REGISTRY, errors)
    baseline = load_json(BASELINE, errors)
    restart = load_json(RESTART, errors)
    try:
        matrix_text = MATRIX.read_text(encoding="utf-8")
    except OSError as exc:
        matrix_text = ""
        errors.append(f"{relative_path(MATRIX)}: 无法读取: {exc}")
    try:
        coverage_text = COVERAGE.read_text(encoding="utf-8")
    except OSError as exc:
        coverage_text = ""
        errors.append(f"{relative_path(COVERAGE)}: 无法读取: {exc}")

    matrix_rows = parse_matrix_rows(matrix_text, errors)
    matrix_ids = set(matrix_rows)

    cases = registry.get("cases")
    require(registry.get("schema_version") == "public-case-registry-v1", "登记表 schema_version 不正确", errors)
    require(registry.get("dataset_type") == "adapted_published_real_case", "登记表 dataset_type 不正确", errors)
    require(isinstance(cases, list) and cases, "登记表 cases 必须是非空数组", errors)

    # 来源、许可和改编政策是病例可复用的前提。 这些字段使用本登记表
    # 内部 JSON Pointer 引用，校验器必须确认引用没有悬空。
    source = registry.get("source")
    license_info = registry.get("license")
    adaptation_policy = registry.get("adaptation_policy")
    require(isinstance(source, dict), "登记表 source 必须是对象", errors)
    require(isinstance(license_info, dict), "登记表 license 必须是对象", errors)
    require(isinstance(adaptation_policy, dict), "登记表 adaptation_policy 必须是对象", errors)
    if isinstance(source, dict):
        for key in ("title", "authors", "journal", "doi", "pmcid", "url", "checked_at"):
            require(bool(source.get(key)), f"登记表 source 缺少有效 {key}", errors)
        require(
            isinstance(source.get("authors"), list) and bool(source.get("authors")),
            "登记表 source.authors 必须是非空数组",
            errors,
        )
    if isinstance(license_info, dict):
        for key in ("name", "url", "checked_at", "attribution_text", "reuse_scope"):
            require(bool(license_info.get(key)), f"登记表 license 缺少有效 {key}", errors)
        require(
            isinstance(license_info.get("attribution_required"), bool),
            "登记表 license.attribution_required 必须是布尔值",
            errors,
        )
        if license_info.get("attribution_required") is True:
            require(bool(license_info.get("attribution_text")), "需要署名时 attribution_text 不能为空", errors)
    if isinstance(adaptation_policy, dict):
        for key in ("summary", "occurred_time_policy"):
            require(bool(adaptation_policy.get(key)), f"登记表 adaptation_policy 缺少有效 {key}", errors)
        for key in ("not_original_record", "not_direct_patient_speech"):
            require(adaptation_policy.get(key) is True, f"登记表 adaptation_policy.{key} 必须为 true", errors)

    referenced_matrix_ids: set[str] = set()
    if isinstance(cases, list):
        groups = {c.get("case_group") for c in cases if isinstance(c, dict)}
        ids = [c.get("case_id") for c in cases if isinstance(c, dict)]
        string_ids = [case_id for case_id in ids if isinstance(case_id, str) and case_id]
        require(len(string_ids) == len(set(string_ids)), "登记表 case_id 必须是非空字符串且唯一", errors)
        require(registry.get("extract_count") == len(cases), "extract_count 与 cases 长度不一致", errors)
        require(registry.get("patient_count") == len(groups), "patient_count 与 case_group 去重数不一致", errors)
        for index, case in enumerate(cases, 1):
            prefix = f"登记表 cases[{index}]"
            require(isinstance(case, dict), f"{prefix} 必须是对象", errors)
            if not isinstance(case, dict):
                continue
            for key in (
                "case_id",
                "case_group",
                "source_ref",
                "license_ref",
                "adaptation_ref",
                "source_kind",
                "input_text",
                "occurred_time",
                "expected_behavior",
                "known_limitations",
                "test_case_ids",
            ):
                require(key in case, f"{prefix} 缺少 {key}", errors)
            require(isinstance(case.get("case_id"), str) and bool(case.get("case_id")), f"{prefix}.case_id 必须是非空字符串", errors)
            require(isinstance(case.get("case_group"), str) and bool(case.get("case_group")), f"{prefix}.case_group 必须是非空字符串", errors)
            require(isinstance(case.get("input_text"), str) and bool(case.get("input_text")), f"{prefix}.input_text 必须是非空字符串", errors)
            require(case.get("source_kind") == "document", f"{prefix} source_kind 必须为 document", errors)
            require(case.get("occurred_time") is None, f"{prefix} occurred_time 必须为 null", errors)
            require(isinstance(case.get("expected_behavior"), dict), f"{prefix}.expected_behavior 必须是对象", errors)
            require(isinstance(case.get("known_limitations"), list) and bool(case.get("known_limitations")), f"{prefix} known_limitations 必须是非空数组", errors)
            require(isinstance(case.get("test_case_ids"), list) and bool(case.get("test_case_ids")), f"{prefix} test_case_ids 必须是非空数组", errors)

            # source_ref 是逐条记录章节位置的内联对象；许可和改编政策则
            # 使用登记表内 JSON Pointer。两种形式都必须能回溯到同一登记。
            source_ref = case.get("source_ref")
            require(isinstance(source_ref, dict), f"{prefix}.source_ref 必须是对象", errors)
            if isinstance(source_ref, dict) and isinstance(source, dict):
                require(
                    source_ref.get("pmcid") == source.get("pmcid"),
                    f"{prefix}.source_ref.pmcid 与登记表 source.pmcid 不一致",
                    errors,
                )
                require(bool(source_ref.get("section")), f"{prefix}.source_ref.section 不能为空", errors)
            for ref_key, expected_target in (
                ("license_ref", license_info),
                ("adaptation_ref", adaptation_policy),
            ):
                reference = case.get(ref_key)
                resolved = resolve_local_ref(registry, reference)
                require(
                    resolved is not None,
                    f"{prefix}.{ref_key} 引用不存在或不是本登记表内部 JSON Pointer: {reference!r}",
                    errors,
                )
                if resolved is not None and expected_target is not None:
                    require(
                        resolved == expected_target,
                        f"{prefix}.{ref_key} 未指向登记表对应的来源/许可/改编对象",
                        errors,
                    )
            referenced_matrix_ids.update(
                validate_case_references(case, prefix, matrix_rows, errors)
            )

    baseline_rows = baseline.get("public_case_rows")
    require(isinstance(baseline_rows, list), "文字基线缺少 public_case_rows 数组", errors)
    require(baseline.get("dataset_version") == registry.get("dataset_version"), "文字基线 dataset_version 与登记表不一致", errors)
    require(baseline.get("patient_count") == registry.get("patient_count"), "文字基线 patient_count 与登记表不一致", errors)
    require(baseline.get("extract_count") == registry.get("extract_count"), "文字基线 extract_count 与登记表不一致", errors)
    if isinstance(cases, list) and isinstance(baseline_rows, list):
        registry_ids = [c.get("case_id") for c in cases if isinstance(c, dict)]
        evidence_ids = [row.get("case_id") for row in baseline_rows if isinstance(row, dict)]
        require(registry_ids == evidence_ids, "登记表与文字基线 case_id 顺序/集合不一致", errors)
        for row in baseline_rows:
            if not isinstance(row, dict):
                continue
            row_id = row.get("case_id")
            matching_case = next((case for case in cases if isinstance(case, dict) and case.get("case_id") == row_id), None)
            require(isinstance(row.get("expected_local_danger"), bool), f"{row_id}: expected_local_danger 必须是布尔值", errors)
            require(isinstance(row.get("actual_local_danger"), bool), f"{row_id}: actual_local_danger 必须是布尔值", errors)
            require(row.get("expected_local_danger") == row.get("actual_local_danger"), f"{row_id}: 预期/实际危险结果不一致", errors)
            if isinstance(matching_case, dict):
                expected_behavior = matching_case.get("expected_behavior")
                if isinstance(expected_behavior, dict) and "local_danger_detected" in expected_behavior:
                    require(
                        row.get("expected_local_danger") == expected_behavior.get("local_danger_detected"),
                        f"{row_id}: 基线预期与登记表 expected_behavior 不一致",
                        errors,
                    )
            require(row.get("source_kind") == "document", f"{row.get('case_id')}: evidence source_kind 不是 document", errors)
            require(row.get("occurred_time") is None, f"{row.get('case_id')}: evidence occurred_time 不是 null", errors)

            danger_value = row.get("expected_local_danger")
            persisted = row.get("danger_notice_persisted_after_confirmation")
            if danger_value is True:
                require(persisted is True, f"{row_id}: 命中危险时提醒持续字段必须为 true", errors)
            elif danger_value is False:
                require(persisted == "not_applicable", f"{row_id}: 未命中病例不应伪造提醒持续断言", errors)

    # 不要求某台机器历史上必然 blocked/passed；只检查证据声明结构、运行结果
    # 与退出码是否互相一致，以及证据中明确声明的环境边界。
    validate_evidence_runs(baseline, "文字基线", errors, warnings)
    validate_evidence_runs(restart, "重启证据", errors, warnings)

    try:
        registry_sha = hashlib.sha256(REGISTRY.read_bytes()).hexdigest()
    except OSError as exc:
        registry_sha = ""
        errors.append(f"{relative_path(REGISTRY)}: 无法计算 SHA-256: {exc}")
    baseline_hashes = baseline.get("environment", {}).get("dataset_sha256") if isinstance(baseline.get("environment"), dict) else None
    require(
        isinstance(baseline_hashes, dict)
        and baseline_hashes.get("data/public_cases/registry.json") == registry_sha,
        "文字基线未声明与当前登记表匹配的 registry SHA-256",
        errors,
    )
    restart_registry_sha = restart.get("input", {}).get("registry_sha256") if isinstance(restart.get("input"), dict) else None
    require(
        isinstance(restart_registry_sha, str) and restart_registry_sha == registry_sha,
        "重启证据未声明与当前登记表匹配的 registry SHA-256",
        errors,
    )
    restart_actual = restart.get("observations", {}).get("actual") if isinstance(restart.get("observations"), dict) else None
    if isinstance(restart.get("status"), str) and restart.get("status").strip().lower() in KNOWN_SUCCESS_STATUSES:
        require(
            isinstance(restart_actual, dict) and restart_actual.get("process_restarted") is True,
            "重启证据声明成功但 observations.actual.process_restarted 不是 true",
            errors,
        )

    for row_id, row in matrix_rows.items():
        row_text = str(row.get("text", ""))
        if row_id.startswith(UNIMPLEMENTED_MATRIX_PREFIXES):
            require("已交付" not in row_text, f"未实现范围被标为已交付: {row_text}", errors)
    if "60 秒强制结束" in matrix_text or "最长 60 秒自动结束" in matrix_text:
        errors.append("测试矩阵恢复了已撤回的 60 秒强制结束规则")
    if "真实 ASR/OCR" not in matrix_text:
        warnings.append("矩阵未显式提及真实 ASR/OCR 未验证")
    for heading in ("## T0–T2", "## T3–T6", "## 最终十项判断标准覆盖"):
        require(heading in coverage_text, f"覆盖表缺少分段: {heading}", errors)
    for status in ("已交付", "条件式交付", "等待用户决定", "明确不在本次范围"):
        require(status in coverage_text, f"覆盖表缺少状态: {status}", errors)

    result = {
        "ok": not errors,
        "registry_cases": len(cases) if isinstance(cases, list) else 0,
        "matrix_ids": len(matrix_rows),
        "referenced_matrix_ids": sorted(referenced_matrix_ids),
        "errors": errors,
        "warnings": warnings,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
