"""Verify the B-side release gate and emit one machine-readable JSON report."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, TextIO


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TIMEOUT_SECONDS = 600
REPORT_SCHEMA_VERSION = "b-release-gate-v1"

Runner = Callable[..., subprocess.CompletedProcess[str]]

_SECRET_ENV_NAME = re.compile(
    r"(?:^|_)(?:TOKEN|KEY|SECRET|PASSWORD|PASSWD|CREDENTIALS?)(?:_|$)",
    re.IGNORECASE,
)
_DATABASE_NAME = re.compile(
    r"(?:\.db|\.sqlite|\.sqlite3)(?:-(?:journal|shm|wal))?$",
    re.IGNORECASE,
)
_CACHE_DIRECTORIES = {
    ".cache",
    ".mypy_cache",
    ".nox",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    "__pycache__",
    "coverage",
}


def subprocess_runner(
    command: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    """Run one gate command without streaming potentially sensitive output."""

    return subprocess.run(
        list(command),
        cwd=cwd,
        env=dict(env),
        capture_output=True,
        check=False,
        text=True,
        timeout=timeout_seconds,
    )


def sanitized_environment(environ: Mapping[str, str]) -> dict[str, str]:
    """Keep normal process settings while removing credential-like variables."""

    clean = {
        name: value
        for name, value in environ.items()
        if _SECRET_ENV_NAME.search(name) is None
    }
    clean["MODEL_PROVIDER"] = "mock"
    clean["NPM_CONFIG_OFFLINE"] = "true"
    clean["NPM_CONFIG_AUDIT"] = "false"
    clean["NPM_CONFIG_FUND"] = "false"
    clean["NPM_CONFIG_UPDATE_NOTIFIER"] = "false"
    return clean


def _run_check(
    name: str,
    command: Sequence[str],
    *,
    repo_root: Path,
    env: Mapping[str, str],
    timeout_seconds: int,
    runner: Runner,
    parser: Callable[[str], list[str]] | None = None,
    default_violation_reason: str | None = None,
) -> dict[str, Any]:
    """Run one check and retain only safe status metadata in the public report."""

    public_command = list(command)
    try:
        result = runner(
            public_command,
            cwd=repo_root,
            env=env,
            timeout_seconds=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        check = {
            "name": name,
            "passed": False,
            "returncode": None,
            "command": public_command,
            "failure": "timeout",
        }
        if parser is not None:
            check["violations"] = []
        return check
    except OSError:
        check = {
            "name": name,
            "passed": False,
            "returncode": None,
            "command": public_command,
            "failure": "command_unavailable",
        }
        if parser is not None:
            check["violations"] = []
        return check

    check = {
        "name": name,
        "passed": result.returncode == 0,
        "returncode": result.returncode,
        "command": public_command,
    }
    if result.returncode != 0:
        check["failure"] = "command_failed"
        if parser is not None:
            check["violations"] = []
        return check
    if parser is not None:
        violations = []
        for path in parser(result.stdout or ""):
            reason = prohibited_path_reason(path) or default_violation_reason
            if reason is not None:
                violations.append({"path": path, "reason": reason})
        check["passed"] = not violations
        check["violations"] = violations
    return check


def run_command_check(
    name: str,
    command: Sequence[str],
    *,
    repo_root: Path,
    env: Mapping[str, str],
    timeout_seconds: int,
    runner: Runner,
) -> dict[str, Any]:
    """Run a command and retain only status metadata in the public report."""

    return _run_check(
        name,
        command,
        repo_root=repo_root,
        env=env,
        timeout_seconds=timeout_seconds,
        runner=runner,
    )


def parse_porcelain_paths(output: str) -> list[str]:
    """Extract all paths, including both sides of porcelain-v1 renames/copies."""

    tokens = output.split("\0")
    paths: list[str] = []
    index = 0
    while index < len(tokens):
        entry = tokens[index]
        index += 1
        if not entry:
            continue
        if len(entry) < 4 or entry[2] != " ":
            continue
        status = entry[:2]
        paths.append(entry[3:])
        if "R" in status or "C" in status:
            if index < len(tokens) and tokens[index]:
                paths.append(tokens[index])
            index += 1
    return paths


def parse_nul_paths(output: str) -> list[str]:
    return [path for path in output.split("\0") if path]


def prohibited_path_reason(path: str) -> str | None:
    """Classify release-prohibited files using repository-relative paths only."""

    normalized = path.replace("\\", "/").removeprefix("./")
    parts = tuple(part.lower() for part in PurePosixPath(normalized).parts)
    if not parts:
        return None

    basename = parts[-1]
    if basename == ".env" or (
        basename.startswith(".env.") and basename != ".env.example"
    ):
        return "environment_file"
    if "node_modules" in parts:
        return "node_modules"
    if any(part in _CACHE_DIRECTORIES or part.endswith(".cache") for part in parts):
        return "cache"
    if basename.endswith((".pyc", ".pyo")) or basename.startswith(".coverage"):
        return "cache"
    if _DATABASE_NAME.search(basename):
        return "runtime_database"
    return None


def path_check(
    name: str,
    command: Sequence[str],
    parser: Callable[[str], list[str]],
    *,
    default_violation_reason: str | None = None,
    repo_root: Path,
    env: Mapping[str, str],
    timeout_seconds: int,
    runner: Runner,
) -> dict[str, Any]:
    """Run one Git inventory and report classified path violations."""

    return _run_check(
        name,
        command,
        repo_root=repo_root,
        env=env,
        timeout_seconds=timeout_seconds,
        runner=runner,
        parser=parser,
        default_violation_reason=default_violation_reason,
    )


def verify_release(
    repo_root: Path,
    *,
    runner: Runner = subprocess_runner,
    environ: Mapping[str, str] | None = None,
    python_executable: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Run every B-side release check and return a JSON-serializable report."""

    root = repo_root.resolve()
    env = sanitized_environment(os.environ if environ is None else environ)
    python = python_executable or sys.executable

    checks: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="b-release-gate-") as temporary:
        temporary_path = Path(temporary)
        env["DB_PATH"] = str(temporary_path / "gate.sqlite3")
        commands = (
            ("pytest", (python, "-m", "pytest", "-q")),
            (
                "mock_evaluation",
                (
                    python,
                    "-m",
                    "backend.evaluate_mock",
                    "--out",
                    str(temporary_path / "mock-result.json"),
                ),
            ),
            (
                "public_case_demo",
                (
                    python,
                    "-m",
                    "scripts.demo",
                    "--out",
                    str(temporary_path / "public-case-demo.json"),
                ),
            ),
            ("npm_ci", ("npm", "ci")),
            ("typescript_contract", ("npm", "run", "check:contracts")),
        )
        for name, command in commands:
            checks.append(
                run_command_check(
                    name,
                    command,
                    repo_root=root,
                    env=env,
                    timeout_seconds=timeout_seconds,
                    runner=runner,
                )
            )

        checks.append(
            path_check(
                "git_status_paths",
                (
                    "git",
                    "status",
                    "--porcelain=v1",
                    "-z",
                    "--untracked-files=all",
                ),
                parse_porcelain_paths,
                default_violation_reason="uncommitted_change",
                repo_root=root,
                env=env,
                timeout_seconds=timeout_seconds,
                runner=runner,
            )
        )
        checks.append(
            path_check(
                "git_tracked_paths",
                ("git", "ls-files", "-z"),
                parse_nul_paths,
                repo_root=root,
                env=env,
                timeout_seconds=timeout_seconds,
                runner=runner,
            )
        )

    passed_count = sum(check["passed"] for check in checks)
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "passed": passed_count == len(checks),
        "summary": {
            "total": len(checks),
            "passed": passed_count,
            "failed": len(checks) - passed_count,
        },
        "checks": checks,
        "limitations": [
            "mock and public-case checks do not verify real-model quality",
            "this gate does not verify browser integration",
            "software checks do not establish clinical safety",
            "repository hygiene checks are path-based, not a content secret scan",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the B-side release gate and print one JSON report.",
        epilog=(
            "Prerequisites: run this from the repository root with Python 3.12; "
            "start with a clean Git worktree and an npm cache that already contains "
            "every package locked by package-lock.json. The verifier runs `npm ci` "
            "in offline mode and does not access the network or call a model "
            "(tests may use local loopback). It forces Mock mode and strips "
            "credential-like environment variables. This gate does not validate "
            "real-model quality, browser integration, or clinical safety. Repository "
            "hygiene detection is path-based, not a content secret scanner."
        ),
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="maximum seconds allowed for each individual command (default: 600)",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    runner: Runner = subprocess_runner,
    environ: Mapping[str, str] | None = None,
    repo_root: Path | None = None,
    python_executable: str | None = None,
    output: TextIO | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")

    report = verify_release(
        Path.cwd() if repo_root is None else repo_root,
        runner=runner,
        environ=environ,
        python_executable=python_executable,
        timeout_seconds=args.timeout_seconds,
    )
    json.dump(report, sys.stdout if output is None else output, ensure_ascii=False)
    (sys.stdout if output is None else output).write("\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
