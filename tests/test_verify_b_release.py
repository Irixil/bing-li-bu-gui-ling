import io
import json
import subprocess
from pathlib import Path

import pytest

from scripts import verify_b_release


class RecordingRunner:
    def __init__(self, results=None):
        self.results = results or {}
        self.calls = []

    def __call__(self, command, *, cwd, env, timeout_seconds):
        command = tuple(command)
        self.calls.append(
            {
                "command": command,
                "cwd": cwd,
                "env": env,
                "timeout_seconds": timeout_seconds,
            }
        )
        result = self.results.get(
            command,
            subprocess.CompletedProcess(command, 0, stdout="", stderr=""),
        )
        if isinstance(result, BaseException):
            raise result
        return result


def command_ending(calls, ending):
    return next(call for call in calls if call["command"][-len(ending) :] == ending)


def test_release_gate_removes_credentials_and_preserves_runtime_settings(tmp_path):
    runner = RecordingRunner()
    verify_b_release.verify_release(
        tmp_path,
        runner=runner,
        environ={
            "PATH": "/usr/bin:/bin",
            "TOKEN": "secret",
            "build_token": "secret",
            "SIGNING_KEY": "secret",
            "MODELSCOPE_ACCESS_TOKEN": "secret",
            "TOKENIZERS_PARALLELISM": "true",
            "UNRELATED_SETTING": "preserved",
        },
        python_executable="/test/python3.12",
    )

    for call in runner.calls:
        assert call["env"]["PATH"] == "/usr/bin:/bin"
        assert call["env"]["TOKENIZERS_PARALLELISM"] == "true"
        assert call["env"]["UNRELATED_SETTING"] == "preserved"
        assert "TOKEN" not in call["env"]
        assert "build_token" not in call["env"]
        assert "SIGNING_KEY" not in call["env"]
        assert "MODELSCOPE_ACCESS_TOKEN" not in call["env"]


def test_release_gate_runs_every_required_check_without_credentials(tmp_path):
    runner = RecordingRunner()
    source_environment = {
        "PATH": "/usr/bin:/bin",
        "DEEPSEEK_API_KEY": "must-not-be-forwarded",
        "MODELSCOPE_ACCESS_TOKEN": "must-not-be-forwarded",
        "MODELSCOPE_TOKEN": "must-not-be-forwarded",
        "GITHUB_TOKEN": "must-not-be-forwarded",
        "NPM_TOKEN": "must-not-be-forwarded",
        "NPM_CONFIG_AUTH_TOKEN": "must-not-be-forwarded",
        "TOKEN": "must-not-be-forwarded",
        "build_token": "must-not-be-forwarded",
        "SIGNING_KEY": "must-not-be-forwarded",
        "TOKENIZERS_PARALLELISM": "preserved",
        "UNRELATED_SETTING": "preserved",
    }

    report = verify_b_release.verify_release(
        tmp_path,
        runner=runner,
        environ=source_environment,
        python_executable="/test/python3.12",
    )

    assert report["passed"] is True
    assert [check["name"] for check in report["checks"]] == [
        "pytest",
        "mock_evaluation",
        "public_case_demo",
        "npm_ci",
        "typescript_contract",
        "git_status_paths",
        "git_tracked_paths",
    ]
    commands = [call["command"] for call in runner.calls]
    assert commands[0] == ("/test/python3.12", "-m", "pytest", "-q")
    assert commands[1][:4] == (
        "/test/python3.12",
        "-m",
        "backend.evaluate_mock",
        "--out",
    )
    assert commands[2][:4] == (
        "/test/python3.12",
        "-m",
        "scripts.demo",
        "--out",
    )
    assert commands[3] == ("npm", "ci")
    assert commands[4] == ("npm", "run", "check:contracts")
    assert commands[5] == (
        "git",
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    )
    assert commands[6] == ("git", "ls-files", "-z")

    for call in runner.calls:
        assert call["cwd"] == tmp_path.resolve()
        assert call["env"]["MODEL_PROVIDER"] == "mock"
        assert call["env"]["PATH"] == "/usr/bin:/bin"
        assert call["env"]["TOKENIZERS_PARALLELISM"] == "preserved"
        assert call["env"]["UNRELATED_SETTING"] == "preserved"
        assert "DEEPSEEK_API_KEY" not in call["env"]
        assert "MODELSCOPE_ACCESS_TOKEN" not in call["env"]
        assert "MODELSCOPE_TOKEN" not in call["env"]
        assert "GITHUB_TOKEN" not in call["env"]
        assert "NPM_TOKEN" not in call["env"]
        assert "NPM_CONFIG_AUTH_TOKEN" not in call["env"]
        assert "TOKEN" not in call["env"]
        assert "build_token" not in call["env"]
        assert "SIGNING_KEY" not in call["env"]


def test_release_gate_runs_remaining_checks_after_a_command_fails(tmp_path):
    pytest_command = ("/test/python3.12", "-m", "pytest", "-q")
    runner = RecordingRunner(
        {
            pytest_command: subprocess.CompletedProcess(
                pytest_command,
                1,
                stdout="one failed\npossibly sensitive child output",
                stderr="failure detail",
            )
        }
    )

    report = verify_b_release.verify_release(
        tmp_path,
        runner=runner,
        environ={"PATH": "/usr/bin:/bin"},
        python_executable="/test/python3.12",
    )

    assert report["passed"] is False
    assert len(runner.calls) == 7
    failed = report["checks"][0]
    assert failed == {
        "name": "pytest",
        "passed": False,
        "returncode": 1,
        "command": ["/test/python3.12", "-m", "pytest", "-q"],
        "failure": "command_failed",
    }
    assert "possibly sensitive" not in json.dumps(report)


@pytest.mark.parametrize(
    ("exception", "failure"),
    [
        (
            subprocess.TimeoutExpired(
                ("npm", "ci"),
                1,
                output="must-not-be-reported",
                stderr="must-not-be-reported",
            ),
            "timeout",
        ),
        (OSError("credential-value-must-not-be-reported"), "command_unavailable"),
    ],
)
def test_release_gate_reports_unavailable_or_timed_out_command_without_stopping(
    tmp_path, exception, failure
):
    npm_ci_command = ("npm", "ci")
    runner = RecordingRunner({npm_ci_command: exception})

    report = verify_b_release.verify_release(
        tmp_path,
        runner=runner,
        environ={
            "PATH": "/usr/bin:/bin",
            "UNRELATED_SETTING": "environment-value-must-not-be-reported",
        },
        python_executable="/test/python3.12",
        timeout_seconds=1,
    )

    assert len(runner.calls) == 7
    failed = next(check for check in report["checks"] if check["name"] == "npm_ci")
    assert failed == {
        "name": "npm_ci",
        "passed": False,
        "returncode": None,
        "command": ["npm", "ci"],
        "failure": failure,
    }
    serialized = json.dumps(report)
    assert "must-not-be-reported" not in serialized
    assert "environment-value-must-not-be-reported" not in serialized


def test_release_gate_rejects_dirty_worktree_and_prohibited_tracked_paths(tmp_path):
    status_command = (
        "git",
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    )
    tracked_command = ("git", "ls-files", "-z")
    runner = RecordingRunner(
        {
            status_command: subprocess.CompletedProcess(
                status_command,
                0,
                stdout=(
                    "?? .env.local\0"
                    "?? runtime/records.sqlite3-wal\0"
                    "?? src/__pycache__/module.pyc\0"
                    "?? node_modules/typescript/bin/tsc\0"
                    "?? docs/allowed.md\0"
                ),
                stderr="",
            ),
            tracked_command: subprocess.CompletedProcess(
                tracked_command,
                0,
                stdout=(
                    ".env.example\0"
                    "data/records.db\0"
                    "frontend/node_modules/package/index.js\0"
                    "backend/server.py\0"
                ),
                stderr="",
            ),
        }
    )

    report = verify_b_release.verify_release(
        tmp_path,
        runner=runner,
        environ={"PATH": "/usr/bin:/bin"},
        python_executable="/test/python3.12",
    )

    assert report["passed"] is False
    status_check = next(
        check for check in report["checks"] if check["name"] == "git_status_paths"
    )
    tracked_check = next(
        check for check in report["checks"] if check["name"] == "git_tracked_paths"
    )
    assert status_check["violations"] == [
        {"path": ".env.local", "reason": "environment_file"},
        {"path": "runtime/records.sqlite3-wal", "reason": "runtime_database"},
        {"path": "src/__pycache__/module.pyc", "reason": "cache"},
        {"path": "node_modules/typescript/bin/tsc", "reason": "node_modules"},
        {"path": "docs/allowed.md", "reason": "uncommitted_change"},
    ]
    assert tracked_check["violations"] == [
        {"path": "data/records.db", "reason": "runtime_database"},
        {
            "path": "frontend/node_modules/package/index.js",
            "reason": "node_modules",
        },
    ]


def test_git_status_parser_checks_both_sides_of_a_rename():
    output = "R  safe-name.txt\0.env\0 M backend/server.py\0"

    assert verify_b_release.parse_porcelain_paths(output) == [
        "safe-name.txt",
        ".env",
        "backend/server.py",
    ]


def test_release_gate_classifies_both_sides_of_a_dirty_rename(tmp_path):
    status_command = (
        "git",
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    )
    runner = RecordingRunner(
        {
            status_command: subprocess.CompletedProcess(
                status_command,
                0,
                stdout="R  safe-name.txt\0.env\0",
                stderr="",
            )
        }
    )

    report = verify_b_release.verify_release(
        tmp_path,
        runner=runner,
        environ={"PATH": "/usr/bin:/bin"},
        python_executable="/test/python3.12",
    )

    status_check = next(
        check for check in report["checks"] if check["name"] == "git_status_paths"
    )
    assert status_check["passed"] is False
    assert status_check["violations"] == [
        {"path": "safe-name.txt", "reason": "uncommitted_change"},
        {"path": ".env", "reason": "environment_file"},
    ]


def test_cli_prints_one_json_report_and_returns_nonzero_on_failure(tmp_path):
    npm_command = ("npm", "run", "check:contracts")
    runner = RecordingRunner(
        {
            npm_command: subprocess.CompletedProcess(
                npm_command,
                127,
                stdout="",
                stderr="npm is unavailable",
            )
        }
    )
    output = io.StringIO()

    exit_code = verify_b_release.main(
        [],
        runner=runner,
        environ={"PATH": "/usr/bin:/bin"},
        repo_root=tmp_path,
        python_executable="/test/python3.12",
        output=output,
    )

    report = json.loads(output.getvalue())
    assert exit_code == 1
    assert report["passed"] is False
    assert output.getvalue().count('"schema_version"') == 1


def test_help_states_offline_prerequisites_and_scope_limitations():
    help_text = " ".join(verify_b_release.build_parser().format_help().split())

    assert "npm ci" in help_text
    assert "npm cache" in help_text
    assert "clean Git worktree" in help_text
    assert "does not access the network" in help_text
    assert "real-model" in help_text
    assert "browser" in help_text
    assert "clinical" in help_text
    assert "path-based" in help_text
