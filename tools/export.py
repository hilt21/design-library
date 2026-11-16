"""Build, check, or sync the Design Library export. Python 3.11+, no dependencies."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IDENTIFIER = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
SOURCE_REPO = re.compile(r"[\w.-]+/[\w.-]+")
SHA = re.compile(r"[0-9a-f]{40}")
FILE = re.compile(r"[A-Z][A-Z-]*\.md")
REPOSITORY = "hilt21/design-library"
CATALOG = "catalog.json"
EXPORT = "exports/index.json"
ROUTER_PACKAGE = "skills/design-library"


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def as_json(path):
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)


def encode(data):
    return (json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def normalized(alias):
    return unicodedata.normalize("NFKC", alias).strip().casefold()


def identifiers(values, field, *, required=False):
    if not isinstance(values, list) or (required and not values):
        raise ValueError(f"{field} must be a list")
    if any(not isinstance(value, str) or not IDENTIFIER.fullmatch(value) for value in values):
        raise ValueError(f"Invalid identifier in {field}")
    if len(values) != len(set(values)):
        raise ValueError(f"Duplicate identifier in {field}")


def check_source(source):
    if set(source) != {"repository", "commit", "path", "license"}:
        raise ValueError("Source requires repository, commit, path, and license")
    path = source["path"]
    if (not SOURCE_REPO.fullmatch(source["repository"]) or not SHA.fullmatch(source["commit"])
            or not source["license"] or "\\" in path
            or any(part in {"", ".", "..", ".git"} for part in path.split("/"))):
        raise ValueError(f"Invalid provenance: {source}")


def checked_files(root, entry):
    entry_id = entry["id"]
    filename = {"skill": "SKILL.md", "instruction": "INSTRUCTIONS.md",
                "prompt": "PROMPT.md"}.get(entry["type"])
    if not filename or entry["entry"] != filename:
        raise ValueError(f"Type and entry path disagree: {entry_id}")
    names = [filename, *entry["dependencies"]]
    if any(not isinstance(name, str) or not FILE.fullmatch(name) for name in names):
        raise ValueError(f"Invalid Markdown filename: {entry_id}")
    if len(names) != len(set(names)):
        raise ValueError(f"Repeated file or self dependency: {entry_id}")
    folder = root / "entries" / entry_id
    if folder.is_symlink() or (root / "entries").is_symlink():
        raise ValueError(f"Symlink in entry: {entry_id}")
    if {file.name for file in folder.iterdir()} != set(names):
        raise ValueError(f"Files differ from declaration: {entry_id}")
    result = {}
    for name in names:
        path = folder / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Invalid entry file: {path}")
        contents = path.read_bytes()
        if not contents or len(contents) > 8000 or b"\r" in contents:
            raise ValueError(f"Expected 1–8000 bytes of UTF-8 with LF endings: {path}")
        header = re.match(r"\A---\n(.+?)\n---\n(.*)\Z", contents.decode(), re.S)
        if not header or not header[2].strip():
            raise ValueError(f"Missing frontmatter or body: {path}")
        if name == filename:
            identity = "name" if entry["type"] == "skill" else "id"
            if f"{identity}: {entry_id}" not in header[1].splitlines():
                raise ValueError(f"Entry frontmatter mismatch: {entry_id}")
        result[path.relative_to(root).as_posix()] = hashlib.sha256(contents).hexdigest()
    return result


def build(root):
    data = as_json(root / CATALOG)
    if data["schema_version"] != 1 or data["repository"] != REPOSITORY:
        raise ValueError("Unsupported catalog identity")
    ids = [entry["id"] for entry in data["entries"]]
    identifiers(ids, "entry IDs", required=True)
    if {path.name for path in (root / "entries").iterdir()} != set(ids):
        raise ValueError("Entry directories differ from catalog")
    aliases = {normalized(entry_id): entry_id for entry_id in ids}
    entries = {}
    for entry in data["entries"]:
        entry_id = entry["id"]
        for field in ("stages", "projects", "required_capabilities"):
            identifiers(entry[field], field, required=field == "stages")
        for alias in entry["aliases"]:
            key = normalized(alias)
            if not key or key in aliases:
                raise ValueError(f"Empty or conflicting alias: {alias!r}")
            aliases[key] = entry_id
        check_source(entry["source"])
        files = checked_files(root, entry)
        prefix = f"entries/{entry_id}/"
        entries[entry_id] = {
            **entry, "entry": prefix + entry["entry"],
            "dependencies": [prefix + name for name in entry["dependencies"]],
            "files": files,
        }
    for reference in data["references"]:
        check_source(reference["source"])
        if not reference["purpose"]:
            raise ValueError("Reference purpose is required")
    return {"schema_version": 1, "repository": REPOSITORY, "entries": entries,
            "references": data["references"]}


def sync(root, router_root, export, expected_sha):
    if not SHA.fullmatch(expected_sha):
        raise ValueError("Sync requires a complete design-library commit SHA")
    # Only published, clean source trees may supply an executable snapshot.
    git = ["git", "-C", str(root)]
    sha = subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output([*git, "status", "--porcelain"], text=True).strip()
    if sha != expected_sha or dirty:
        raise ValueError("Design Library checkout must be clean and match --source-sha")
    target = router_root / ROUTER_PACKAGE
    if not (router_root / "project-router.yaml").is_file() or not (target / "SKILL.md").is_file():
        raise ValueError("Destination requires the project-router Design Library adapter")
    selected = {entry_id: entry for entry_id, entry in export["entries"].items()
                if "content-studio" in entry["projects"]}
    if not selected:
        raise ValueError("No Design Library exports for content-studio")
    if target.is_symlink() or (target / "entries").is_symlink() or (target / "index.json").is_symlink():
        raise ValueError("Symlink in router destination")
    if (target / "entries").exists():
        shutil.rmtree(target / "entries")
    for entry in selected.values():
        for path in entry["files"]:
            destination = target / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((root / path).read_bytes())
    (target / "index.json").write_bytes(encode({
        "schema_version": 1, "repository": REPOSITORY, "commit_sha": sha, "entries": selected,
    }))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--check", action="store_true")
    actions.add_argument("--write", action="store_true")
    actions.add_argument("--sync-router", type=Path)
    parser.add_argument("--source-sha")
    args = parser.parse_args()
    try:
        export = build(ROOT)
        expected = encode(export)
        if args.write:
            (ROOT / EXPORT).write_bytes(expected)
        elif (ROOT / EXPORT).read_bytes() != expected:
            raise ValueError("Stale export. Review changes and run --write.")
        if args.sync_router:
            sync(ROOT, args.sync_router.resolve(), export, args.source_sha or "")
        print(f"Design Library: {len(export['entries'])} entries, "
              f"{len(export['references'])} references validated")
    except (KeyError, TypeError, ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f"Design Library: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
