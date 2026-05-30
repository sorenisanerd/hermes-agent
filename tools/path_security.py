"""Shared path validation helpers for tool implementations.

Extracts the ``resolve() + relative_to()`` and ``..`` traversal check
patterns previously duplicated across skill_manager_tool, skills_tool,
skills_hub, cronjob_tools, and credential_files.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def validate_within_dir(path: Path, root: Path) -> Optional[str]:
    """Ensure *path* resolves to a location within *root*.

    Returns an error message string if validation fails, or ``None`` if the
    path is safe.  Uses ``Path.resolve()`` to follow symlinks and normalize
    ``..`` components.

    Usage::

        error = validate_within_dir(user_path, allowed_root)
        if error:
            return json.dumps({"error": error})
    """
    try:
        resolved = path.resolve()
        root_resolved = root.resolve()
        resolved.relative_to(root_resolved)
    except (ValueError, OSError) as exc:
        return f"Path escapes allowed directory: {exc}"
    return None


def has_traversal_component(path_str: str) -> bool:
    """Return True if *path_str* contains ``..`` traversal components.

    Quick check for obvious traversal attempts before doing full resolution.
    """
    parts = Path(path_str).parts
    return ".." in parts


def resolve_cron_script_path(
    script: str, hermes_home: Path
) -> tuple[Optional[Path], Optional[str]]:
    """Resolve a cron job script path to an absolute, validated Path.

    Supports two formats:

    * ``<filename>`` — resolved within ``<hermes_home>/scripts/``
      (existing behaviour).
    * ``skills/<skill_name>/<relative_path>`` — resolved within the
      named skill's ``scripts/`` directory.

    Returns ``(resolved_path, None)`` on success or
    ``(None, error_message)`` on failure.
    """
    raw = script.strip()
    if not raw:
        return None, "Script path is empty"

    # --- skills/<skill>/<path> convention ---
    if raw.startswith("skills/"):
        parts = raw.split("/", 2)  # → ["skills", "<skill>", "<rest>"]
        if len(parts) < 3 or not parts[1] or not parts[2]:
            return (
                None,
                "skills/ path must include skill name and script path "
                "(e.g. skills/google-calendar/calendar-nudge.sh)",
            )
        skill_name = parts[1]
        rest = parts[2]

        # Locate the skill directory by scanning for a matching SKILL.md
        skills_root = hermes_home / "skills"
        if not skills_root.exists():
            return None, f"Skills directory not found: {skills_root}"

        skill_dir: Optional[Path] = None
        # Check flat layout: skills/<name>/
        flat_candidate = (skills_root / skill_name).resolve()
        if flat_candidate.is_dir() and (flat_candidate / "SKILL.md").exists():
            skill_dir = flat_candidate
        else:
            # Check nested layout: skills/<category>/<name>/
            for cat_dir in skills_root.iterdir():
                if not cat_dir.is_dir():
                    continue
                candidate = (cat_dir / skill_name).resolve()
                if candidate.is_dir() and (candidate / "SKILL.md").exists():
                    skill_dir = candidate
                    break

        if skill_dir is None:
            return None, f"Skill '{skill_name}' not found in skills directory"

        # Resolve <skill_dir>/scripts/<rest>
        resolved = (skill_dir / "scripts" / rest).resolve()
        containment_error = validate_within_dir(resolved, skill_dir / "scripts")
        if containment_error:
            return None, f"Script path escapes skill's scripts/ directory: {containment_error}"
        return resolved, None

    # --- Default: <hermes_home>/scripts/<path> ---
    scripts_dir = hermes_home / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    resolved = (scripts_dir / raw).resolve()
    containment_error = validate_within_dir(resolved, scripts_dir)
    if containment_error:
        return (
            None,
            f"Script path escapes the scripts directory ({scripts_dir}): {containment_error}",
        )
    return resolved, None
