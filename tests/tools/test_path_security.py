"""Unit tests for tools.path_security.resolve_cron_script_path.

Covers the two accepted forms and their failure modes:

* ``<filename>`` — resolved within ``<hermes_home>/scripts/``
* ``skills/<skill_name>/<relative_path>`` — resolved within the named
  skill's ``scripts/`` directory (flat or nested skill layouts)

Security contract: a script path must never resolve outside its allowed
root (scripts dir / skill scripts dir), regardless of ``..`` traversal,
absolute path injection, or symlink escape.
"""

from __future__ import annotations

from pathlib import Path

from tools.path_security import resolve_cron_script_path


# ---------------------------------------------------------------------------
# Default form: <hermes_home>/scripts/<filename>
# ---------------------------------------------------------------------------


def test_empty_script_is_rejected(tmp_path):
    resolved, error = resolve_cron_script_path("", tmp_path)
    assert resolved is None
    assert error is not None
    assert "empty" in error.lower()


def test_plain_filename_resolves_within_scripts_dir(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "job.py").write_text("print('hi')")

    resolved, error = resolve_cron_script_path("job.py", tmp_path)
    assert error is None
    assert resolved == (tmp_path / "scripts" / "job.py").resolve()


def test_scripts_dir_auto_created(tmp_path):
    resolved, error = resolve_cron_script_path("job.py", tmp_path)
    assert error is None
    assert resolved == (tmp_path / "scripts" / "job.py").resolve()
    assert (tmp_path / "scripts").is_dir()


def test_traversal_outside_scripts_dir_rejected(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "evil.py").write_text("")

    resolved, error = resolve_cron_script_path("../evil.py", tmp_path)
    assert resolved is None
    assert error is not None
    assert "Blocked: script path resolves outside the scripts directory" in error


def test_absolute_path_injection_rejected(tmp_path):
    resolved, error = resolve_cron_script_path("/etc/passwd", tmp_path)
    assert resolved is None
    assert error is not None
    assert "escapes" in error


# ---------------------------------------------------------------------------
# skills/<skill>/<path> form
# ---------------------------------------------------------------------------


def _make_flat_skill(home: Path, name: str) -> None:
    skill_dir = home / "skills" / name
    (skill_dir / "scripts").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# skill")
    (skill_dir / "scripts" / "nudge.sh").write_text("#!/bin/sh\n")


def test_flat_skill_resolves(tmp_path):
    _make_flat_skill(tmp_path, "cal")

    resolved, error = resolve_cron_script_path("skills/cal/nudge.sh", tmp_path)
    assert error is None
    assert resolved == (tmp_path / "skills" / "cal" / "scripts" / "nudge.sh").resolve()


def test_nested_skill_resolves(tmp_path):
    skill_dir = tmp_path / "skills" / "productivity" / "cal"
    (skill_dir / "scripts").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# skill")
    (skill_dir / "scripts" / "nudge.sh").write_text("#!/bin/sh\n")

    resolved, error = resolve_cron_script_path("skills/cal/nudge.sh", tmp_path)
    assert error is None
    assert resolved == (skill_dir / "scripts" / "nudge.sh").resolve()


def test_missing_skill_rejected(tmp_path):
    # skills/ exists (with another skill) but the named skill is absent
    _make_flat_skill(tmp_path, "cal")
    resolved, error = resolve_cron_script_path("skills/nope/x.sh", tmp_path)
    assert resolved is None
    assert error is not None
    assert "'nope' not found" in error


def test_skill_path_without_script_part_rejected(tmp_path):
    _make_flat_skill(tmp_path, "cal")
    resolved, error = resolve_cron_script_path("skills/cal", tmp_path)
    assert resolved is None
    assert error is not None
    assert "must include skill name and script path" in error


def test_skill_traversal_escape_rejected(tmp_path):
    _make_flat_skill(tmp_path, "cal")
    (tmp_path / "evil.sh").write_text("")

    resolved, error = resolve_cron_script_path("skills/cal/../../evil.sh", tmp_path)
    assert resolved is None
    assert error is not None
    assert "Blocked: script path resolves outside the skill's scripts directory" in error


def test_missing_skills_root_rejected(tmp_path):
    # No skills/ directory at all
    resolved, error = resolve_cron_script_path("skills/cal/nudge.sh", tmp_path)
    assert resolved is None
    assert error is not None
    assert "Skills directory not found" in error
