"""Helpers shared by judge_scope_over_inclusion_check.py and judge_scope_under_inclusion_check.py.

They were defined in judge_file_scope_breadth_check.py, which was removed on 2026-10-17 (see "Retired checks" in
docs/QC-SCRIPT-REGISTRY.md). The code below is copied unchanged: the SVC-PC judge.toml group loader (weight-preserving,
parsed directly with tomllib), the instruction.md loader and the deliverable-section marker.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

# A "## Graded deliverable filenames" heading or a "Submit the graded deliverable(s) using..." sentence marks the start of
# the OUTPUT-naming section of instruction.md, not source material.
DELIVERABLE_MARKER_RE = re.compile(
    r"##?\s*Graded deliverable filenames|Submit the graded deliverables?\s+using",
    re.IGNORECASE,
)


def _basename(p) -> str:
    return Path(str(p).replace("\\", "/")).name.lower()


def _load_instruction(task_dir: Path) -> str | None:
    p = task_dir / "instruction.md"
    if not p.is_file():
        return None
    return p.read_text(encoding="utf-8", errors="replace")


def _load_svc_pc_groups(task_dir: Path):
    """Every tests/deliverables*/judge.toml under a task dir, parsed directly via tomllib.
    Returns a list of {path, files, criteria: [{name, description, weight}], parse_error}.
    Deliberately NOT rubric_text_lint.load_judge_files -- see module docstring Provenance for
    why this script needs its own copy (weight preservation)."""
    out = []
    tests_dir = task_dir / "tests"
    if not tests_dir.is_dir():
        return out
    for jt in sorted(tests_dir.glob("deliverables*/judge.toml")):
        rel = str(jt.relative_to(task_dir)).replace("\\", "/")
        try:
            data = tomllib.loads(jt.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001 -- never let one bad file kill the batch
            out.append(
                {"path": rel, "files": [], "criteria": [], "parse_error": str(e)}
            )
            continue
        judge = data.get("judge") or {}
        files = judge.get("files") or []
        criteria = [
            {
                "name": c.get("name"),
                "description": c.get("description") or "",
                "weight": c.get("weight"),
            }
            for c in data.get("criterion") or []
        ]
        out.append(
            {"path": rel, "files": files, "criteria": criteria, "parse_error": None}
        )
    return out


def _has_svc_pc_config(task_dir: Path) -> bool:
    tests_dir = task_dir / "tests"
    return tests_dir.is_dir() and any(tests_dir.glob("deliverables*/judge.toml"))


def _weight_sum(criteria) -> float:
    total = 0.0
    for c in criteria:
        w = c.get("weight")
        if isinstance(w, (int, float)):
            total += w
    return round(total, 4)
