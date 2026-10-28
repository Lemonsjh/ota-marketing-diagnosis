"""Export shared course text and a small allowlist, never hotel/session data."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

APPROVED_COURSES = frozenset("""
BG-001 EC-002 EC-005 EC-007 EC-010 EC-012 EC-013 EC-014 EC-017 EC-018
MK-001 OP-003 OP-004 OP-006 OP-008 OP-009 OP-011 OP-012 OP-013 OP-014
OP-019 RM-001
""".split())


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def course_parts(text: str) -> tuple[dict, str]:
    match = re.match(r"\A\ufeff?---\r?\n(.*?)\r?\n---\r?\n(.*)\Z", text, re.S)
    if not match:
        raise ValueError("course metadata is missing")
    fields = {}
    for line in match[1].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key in {"doc_id", "title", "source_review_issue_count", "scope"}:
            fields[key] = json.loads(value.strip())
    return fields, match[2].strip() + "\n"


def export_courses(source: Path, target: Path) -> dict:
    """Write the approved courses to a fixed directory; leave drafts untouched."""
    courses = {}
    for path in sorted(source.rglob("*.md")):
        meta, body = course_parts(path.read_text(encoding="utf-8"))
        code = meta.get("doc_id")
        if code not in APPROVED_COURSES:
            continue
        if code in courses or meta.get("scope") != "shared" or meta.get("source_review_issue_count") != 0:
            raise ValueError("approved course is duplicated or requires review")
        if not body.startswith("# ") or not meta.get("title"):
            raise ValueError("course title or body is missing")
        courses[code] = (meta, body)
    if set(courses) != APPROVED_COURSES:
        raise ValueError("approved course set is incomplete")
    directory = target / "memory"
    directory.mkdir(parents=True, exist_ok=True)
    for code, (_, body) in sorted(courses.items()):
        (directory / f"{code}.md").write_text(body, encoding="utf-8", newline="\n")
    codes = sorted(courses)
    (target / "courses.json").write_text(json.dumps(codes, indent=2), encoding="utf-8")
    return {"documents": len(codes)}


def load_courses(root: Path) -> dict[str, dict]:
    codes = json.loads((root / "courses.json").read_text(encoding="utf-8-sig"))
    if (not isinstance(codes, list) or not codes
            or any(not isinstance(code, str) or not re.fullmatch(r"[A-Z]{2}-\d{3}", code) for code in codes)
            or len(set(codes)) != len(codes)):
        raise ValueError("invalid course list")
    root = root.resolve()
    result = {}
    for code in codes:
        relative = f"memory/{code}.md"
        path = (root / relative).resolve()
        if not path.is_relative_to(root / "memory"):
            raise ValueError("course is outside the knowledge directory")
        body = path.read_bytes().decode("utf-8")
        title = body.splitlines()[0].lstrip("\ufeff") if body else ""
        if not title.startswith("# ") or not title[2:].strip():
            raise ValueError("course title is missing")
        result[relative] = {"doc_id": code, "title": title[2:].strip(), "sha256": digest(body)}
    return result
