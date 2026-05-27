"""CLI integration tests for main.py — subprocess-based, testing terminal output and DB state."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

# Worktree root — used as cwd for all subprocess calls
PROJECT_ROOT = Path(__file__).parent.parent.parent


def run_main(*args: str, db_path: str | None = None) -> subprocess.CompletedProcess:
    """Run main.py via uv run python main.py <args> and capture output."""
    test_env = os.environ.copy()
    # Use a caller-provided DB path (temp file) so each test is isolated
    if db_path:
        test_env["DB_PATH"] = db_path

    return subprocess.run(
        ["uv", "run", "python", "main.py", *args],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        env=test_env,
    )


def test_help_shows_dry_run_flag():
    """--help output must include --dry-run flag."""
    result = subprocess.run(
        ["uv", "run", "python", "main.py", "--help"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0
    assert "--dry-run" in result.stdout


def test_dry_run_prints_queued_line(tmp_path):
    """--dry-run stdout must contain at least one QUEUED line with a job title."""
    db = str(tmp_path / "test_cli_queued.db")
    result = run_main("--dry-run", db_path=db)
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "QUEUED" in result.stdout, f"stdout: {result.stdout}"


def test_dry_run_prints_rejected_line(tmp_path):
    """--dry-run stdout must contain at least one REJECTED: line."""
    db = str(tmp_path / "test_cli_rejected.db")
    result = run_main("--dry-run", db_path=db)
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "REJECTED:" in result.stdout, f"stdout: {result.stdout}"


def test_no_dry_run_no_terminal_output(tmp_path):
    """Running without --dry-run must NOT print QUEUED or REJECTED: to stdout."""
    db = str(tmp_path / "test_cli_live.db")
    result = run_main(db_path=db)
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "QUEUED" not in result.stdout, f"stdout contained QUEUED: {result.stdout}"
    assert "REJECTED:" not in result.stdout, f"stdout contained REJECTED:: {result.stdout}"
