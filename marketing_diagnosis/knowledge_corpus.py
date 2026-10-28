"""Export the explicitly approved course release, never hotel/session data."""
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
RELEASE_VERSION = "2026-10-28-internal-r1"


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
    """Create a new immutable release; leave all original drafts untouched."""
    if target.exists():
        raise ValueError("release target must be new")
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
    directory = target / "workspace" / "memory" / "courses"
    directory.mkdir(parents=True)
    documents = []
    for code, (meta, body) in sorted(courses.items()):
        relative = f"memory/courses/{code}.md"
        (target / "workspace" / relative).write_text(body, encoding="utf-8", newline="\n")
        documents.append({"doc_id": code, "title": meta["title"], "path": relative,
                          "sha256": digest(body), "status": "internal_reference"})
    manifest = {"version": RELEASE_VERSION, "scope": "shared_courses_only", "documents": documents}
    (target / "release.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def load_release(root: Path) -> dict[str, dict]:
    manifest = json.loads((root / "release.json").read_text(encoding="utf-8"))
    if manifest.get("version") != RELEASE_VERSION or manifest.get("scope") != "shared_courses_only":
        raise ValueError("unknown course release")
    docs = manifest.get("documents", [])
    if len(docs) != len(APPROVED_COURSES) or {d.get("doc_id") for d in docs} != APPROVED_COURSES:
        raise ValueError("release course set changed")
    workspace = (root / "workspace").resolve()
    result = {}
    for doc in docs:
        relative = f"memory/courses/{doc['doc_id']}.md"
        path = (workspace / relative).resolve()
        if (doc.get("path") != relative or doc.get("status") != "internal_reference"
                or not path.is_relative_to(workspace) or digest(path.read_text(encoding="utf-8")) != doc.get("sha256")):
            raise ValueError("course is outside the release or has changed")
        result[relative] = doc
    return result
