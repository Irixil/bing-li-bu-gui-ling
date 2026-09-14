"""Validate the current public-case registry and backend QA documentation.

This command is deliberately offline and read-only. It never starts the service,
reads credentials, or upgrades historical evidence to current proof.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data/public_cases/registry.json"
RUNTIME_CASES = ROOT / "data/public_cases/cases.json"
MATRIX = ROOT / "docs/qa/test-matrix.md"
COVERAGE = ROOT / "docs/qa/coverage.md"
P1 = ROOT / "docs/team/P1-COMPLEX-IMAGE-RECOGNITION.md"

ID_RE = re.compile(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+")
REQUIRED_MATRIX_IDS = {
    "CASE-PUBLIC-01",
    "CASE-PUBLIC-02",
    "CASE-PUBLIC-03",
    "TEXT-422-01",
    "TEXT-RETRY-01",
    "TEXT-IDEMP-01",
    "TEXT-VERSION-01",
    "TEXT-HISTORY-01",
    "TEXT-BACKUP-01",
    "MEDIA-SAVE-01",
    "MEDIA-IDEMP-01",
    "MEDIA-BACKUP-01",
    "MEDIA-RECOGNITION-01",
    "REAL-ONLINE-01",
    "BROWSER-WEBM-01",
    "MOBILE-01",
    "P1-COMPLEX-IMAGE-01",
}


def load_object(path: Path, errors: list[str]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{path.relative_to(ROOT)}: 无法读取 JSON: {exc}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{path.relative_to(ROOT)}: 顶层必须是对象")
        return {}
    return value


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def matrix_ids(text: str, errors: list[str]) -> set[str]:
    found: set[str] = set()
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.lstrip().startswith("|"):
            continue
        first = line.strip().strip("|").split("|", 1)[0].strip().strip(chr(96))
        if not ID_RE.fullmatch(first):
            continue
        if first in found:
            errors.append(f"docs/qa/test-matrix.md:{line_number}: 用例 ID 重复: {first}")
        found.add(first)
    return found


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    registry = load_object(REGISTRY, errors)
    runtime = load_object(RUNTIME_CASES, errors)

    try:
        matrix_text = MATRIX.read_text(encoding="utf-8")
        coverage_text = COVERAGE.read_text(encoding="utf-8")
        p1_text = P1.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"QA 文档读取失败: {exc}")
        matrix_text = coverage_text = p1_text = ""

    ids = matrix_ids(matrix_text, errors)
    require(
        REQUIRED_MATRIX_IDS <= ids,
        f"测试矩阵缺少用例: {sorted(REQUIRED_MATRIX_IDS - ids)}",
        errors,
    )
    for stale in ("71 passed", "媒体功能尚未实现", "前端实现尚未提交"):
        require(
            stale not in matrix_text + coverage_text,
            f"当前 QA 资料仍包含旧结论: {stale}",
            errors,
        )

    require(
        registry.get("schema_version") == "public-case-registry-v1",
        "登记表 schema_version 不正确",
        errors,
    )
    require(
        registry.get("dataset_type") == "adapted_published_real_case",
        "登记表必须明确为公开发表病例改编",
        errors,
    )
    require(
        registry.get("patient_count") == 1,
        "登记表必须明确 3 段来自 1 位公开患者",
        errors,
    )
    source = registry.get("source")
    license_info = registry.get("license")
    require(
        isinstance(source, dict)
        and all(source.get(key) for key in ("title", "authors", "doi", "pmcid", "url")),
        "登记表来源信息不完整",
        errors,
    )
    require(
        isinstance(license_info, dict)
        and license_info.get("name") == "CC BY 4.0"
        and bool(license_info.get("attribution_text")),
        "登记表许可或署名不完整",
        errors,
    )

    registered = registry.get("cases")
    runtime_rows = runtime.get("cases")
    require(
        isinstance(registered, list) and bool(registered),
        "登记表 cases 必须是非空数组",
        errors,
    )
    require(
        isinstance(runtime_rows, list) and bool(runtime_rows),
        "运行夹具 cases 必须是非空数组",
        errors,
    )
    registered = registered if isinstance(registered, list) else []
    runtime_rows = runtime_rows if isinstance(runtime_rows, list) else []
    require(
        registry.get("dataset_version") == runtime.get("dataset_version"),
        "登记表与运行夹具 dataset_version 不一致",
        errors,
    )
    require(
        registry.get("extract_count") == len(registered) == len(runtime_rows),
        "公开病例条目数量不一致",
        errors,
    )

    runtime_by_id = {
        row.get("id"): row for row in runtime_rows if isinstance(row, dict)
    }
    seen: set[str] = set()
    referenced: set[str] = set()
    for index, case in enumerate(registered, 1):
        context = f"registry.cases[{index}]"
        if not isinstance(case, dict):
            errors.append(f"{context} 必须是对象")
            continue
        case_id = case.get("case_id")
        require(
            isinstance(case_id, str) and bool(case_id),
            f"{context}.case_id 无效",
            errors,
        )
        require(case_id not in seen, f"登记表 case_id 重复: {case_id}", errors)
        seen.add(case_id)
        row = runtime_by_id.get(case_id)
        require(isinstance(row, dict), f"运行夹具缺少 {case_id}", errors)
        if isinstance(row, dict):
            for registry_key, runtime_key in (
                ("case_group", "case_group"),
                ("source_kind", "source_kind"),
                ("input_text", "input"),
            ):
                require(
                    case.get(registry_key) == row.get(runtime_key),
                    f"{case_id}: {registry_key} 与运行夹具不一致",
                    errors,
                )
            source_ref = case.get("source_ref")
            require(
                isinstance(source_ref, dict)
                and source_ref.get("section") == row.get("source_section"),
                f"{case_id}: 来源章节不一致",
                errors,
            )
            expected = case.get("expected_behavior")
            require(
                isinstance(expected, dict)
                and expected.get("local_danger_detected")
                == row.get("expected_local_danger"),
                f"{case_id}: 危险预期不一致",
                errors,
            )

        refs = case.get("test_case_ids")
        require(
            isinstance(refs, list) and bool(refs),
            f"{case_id}: 缺少测试用例引用",
            errors,
        )
        if isinstance(refs, list):
            for ref in refs:
                require(
                    isinstance(ref, str) and ref in ids,
                    f"{case_id}: 测试用例引用不存在: {ref}",
                    errors,
                )
                if isinstance(ref, str):
                    referenced.add(ref)
        require(
            case.get("occurred_time") is None,
            f"{case_id}: 未知发生时间必须为 null",
            errors,
        )
        require(
            bool(case.get("runtime_fixture_ref")),
            f"{case_id}: 缺少运行夹具引用",
            errors,
        )
        require(
            bool(case.get("evidence_ref")),
            f"{case_id}: 缺少当前证据引用",
            errors,
        )

    heart = next(
        (
            case
            for case in registered
            if isinstance(case, dict)
            and case.get("case_id") == "PMC12890330-02"
        ),
        {},
    )
    heart_expected = (
        heart.get("expected_behavior", {}) if isinstance(heart, dict) else {}
    )
    require(
        heart_expected.get("local_danger_detected") is False,
        "心率病例不能伪装成已触发急救规则",
        errors,
    )
    require(
        heart_expected.get("clinical_review_required") is True,
        "心率病例必须保留专业复核候选",
        errors,
    )
    require(
        heart_expected.get("handoff_contains_unresolved_clinical_review") is True,
        "心率病例交接必须保留未解决专业复核",
        errors,
    )

    require(
        "不进入当前 MVP" in p1_text and "尚未实现" in p1_text,
        "P1 文档必须明确 MVP 外且未实现",
        errors,
    )
    require(
        "不能按普通 OCR" in p1_text and "不替代医生诊断" in p1_text,
        "P1 文档缺少复杂图像安全边界",
        errors,
    )
    require(
        "Mock" in coverage_text and "临床" in coverage_text and "生产" in coverage_text,
        "覆盖表缺少证据边界",
        errors,
    )

    result = {
        "ok": not errors,
        "registry_cases": len(registered),
        "runtime_cases": len(runtime_rows),
        "matrix_ids": len(ids),
        "referenced_case_ids": sorted(referenced),
        "errors": errors,
        "warnings": warnings,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
