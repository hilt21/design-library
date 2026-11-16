"""Validate design packages and generate a portable, versioned catalog."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
REPOSITORY = "hilt21/design-library"
EXPORT = "exports/index.json"


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


def digest(data):
    return hashlib.sha256(data).hexdigest()


def normalized(value):
    import unicodedata
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Aliases must be nonempty strings")
    return unicodedata.normalize("NFKC", value).strip().casefold()


def strings(values, field, *, identifiers=False, required=False):
    if (not isinstance(values, list) or (required and not values)
            or any(not isinstance(v, str) or not v for v in values)
            or len(values) != len(set(values))):
        raise ValueError(f"{field} needs unique nonempty strings")
    if identifiers and any(not ID.fullmatch(v) for v in values):
        raise ValueError(f"Invalid ID in {field}")
    return values


def safe_path(root, name):
    if (not isinstance(name, str) or not name or "\\" in name
            or any(part in {"", ".", "..", ".git"} for part in name.split("/"))
            or PurePosixPath(name).is_absolute()):
        raise ValueError(f"Invalid relative path: {name!r}")
    target = root
    for part in name.split("/"):
        target /= part
        if target.is_symlink():
            raise ValueError(f"Symlink in package path: {name}")
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Path escapes package: {name}")
    return target


def inventory(root):
    files = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        safe_path(root, rel)
        if path.is_file():
            files[rel] = digest(path.read_bytes())
    return files


def check_source(source):
    if (not isinstance(source, dict) or not re.fullmatch(r"[\w.-]+/[\w.-]+", str(source.get("repository", "")))
            or not SHA.fullmatch(str(source.get("commit", ""))) or not source.get("license")):
        raise ValueError("Source needs a repository, full commit, path and license")
    safe_path(ROOT, source["path"])


def build(root):
    data = as_json(root / "catalog.json")
    if data.get("schema_version") != 2 or data.get("repository") != REPOSITORY:
        raise ValueError("Unsupported catalog identity")
    ids = strings([e["id"] for e in data["entries"]], "entry IDs", identifiers=True, required=True)
    if set(p.name for p in (root / "entries").iterdir()) != set(ids):
        raise ValueError("Entry directories differ from catalog")
    aliases = {normalized(eid) for eid in ids}
    entries = {}
    for entry in data["entries"]:
        eid = entry["id"]
        for field in ("domains", "stages", "required_capabilities"):
            strings(entry[field], field, identifiers=True, required=field != "required_capabilities")
        strings(entry["aliases"], "aliases")
        for alias in entry["aliases"]:
            key = normalized(alias)
            if key in aliases:
                raise ValueError(f"Conflicting alias: {alias}")
            aliases.add(key)
        if "projects" in entry:
            raise ValueError("Project bindings belong to the consumer")
        for field in ("inputs", "outputs", "cases"):
            strings(entry[field], field, required=True)
        if not isinstance(entry.get("description"), str) or not entry["description"]:
            raise ValueError(f"Missing description: {eid}")
        check_source(entry["source"])
        adaptation = entry["adaptation"]
        if adaptation["relationship"] not in {"adapted", "reference", "original"}:
            raise ValueError(f"Unknown source relationship: {eid}")
        for field in ("retained", "changed", "omitted"):
            strings(adaptation[field], field)
        expected = {"skill": "SKILL.md", "instruction": "INSTRUCTIONS.md", "prompt": "PROMPT.md"}.get(entry["type"])
        if entry["entry"] != expected:
            raise ValueError(f"Type and entry disagree: {eid}")
        folder = safe_path(root, f"entries/{eid}")
        files = inventory(folder)
        required = strings(entry["required"], "required")
        resources = entry["resources"]
        if not isinstance(resources, dict) or any(not purpose for purpose in resources.values()):
            raise ValueError(f"Invalid optional resources: {eid}")
        paths = [entry["entry"], *required, *resources]
        if len(paths) != len(set(paths)) or set(paths) != set(files):
            raise ValueError(f"Files differ from declaration or self dependency: {eid}")
        for path in paths:
            file = safe_path(folder, path)
            if file.suffix not in {".md", ".json", ".txt"}:
                raise ValueError(f"Unsupported resource type: {path}")
            text = file.read_text(encoding="utf-8")
            if not text.strip():
                raise ValueError(f"Empty resource: {path}")
            if file.suffix == ".json":
                as_json(file)
        text = (folder / entry["entry"]).read_text()
        header = re.match(r"\A---\n(.+?)\n---\n(.+)\Z", text, re.S)
        identity = "name" if entry["type"] == "skill" else "id"
        if not header or f"{identity}: {eid}" not in header[1].splitlines():
            raise ValueError(f"Entry frontmatter mismatch: {eid}")
        for imported in entry.get("imported_files", []):
            if imported["local"] not in files or files[imported["local"]] != imported["sha256"]:
                raise ValueError(f"Imported file drift: {eid}")
            safe_path(root, imported["upstream"])
        entries[eid] = {**entry, "files": files, "content_sha256": digest(encode(files))}
    for reference in data["references"]:
        check_source(reference["source"])
    return {"schema_version": 2, "repository": REPOSITORY, "entries": entries,
            "references": data["references"]}


def export_files(data):
    descriptors = {}
    result = {}
    for eid, entry in data["entries"].items():
        path = f"exports/entries/{eid}.json"
        contents = encode(entry)
        result[path] = contents
        descriptors[eid] = {key: entry[key] for key in ("id", "description", "type", "domains", "stages", "aliases")}
        descriptors[eid].update({"manifest": path, "sha256": digest(contents)})
    result[EXPORT] = encode({"schema_version": 2, "repository": REPOSITORY,
                            "entries": descriptors, "references": data["references"]})
    return result


def check_export(root, expected):
    actual = inventory(root / "exports")
    wanted = {path.removeprefix("exports/"): digest(content) for path, content in expected.items()}
    if actual != wanted:
        raise ValueError("Stale export. Review changes and run --write.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--check", action="store_true")
    actions.add_argument("--write", action="store_true")
    actions.add_argument("--sync-router", type=Path)
    parser.add_argument("--source-sha")
    args = parser.parse_args()
    try:
        data = build(ROOT)
        expected = export_files(data)
        if args.write:
            for path, contents in expected.items():
                file = ROOT / path
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(contents)
            for file in (ROOT / "exports").rglob("*.json"):
                if file.relative_to(ROOT).as_posix() not in expected:
                    file.unlink()
        else:
            check_export(ROOT, expected)
        if args.sync_router:
            from tools.sync import sync
            sync(ROOT, args.sync_router.resolve(), data, args.source_sha or "")
        print(f"Design Library: {len(data['entries'])} entries validated")
    except (KeyError, TypeError, ValueError, OSError) as exc:
        print(f"Design Library: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
