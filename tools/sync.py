"""Commit an immutable package then atomically replace its pointer. POSIX maintenance CLI."""
from __future__ import annotations

import fcntl
import os
import subprocess
import tempfile
from pathlib import Path

from tools.export import SHA, as_json, digest, encode, inventory, safe_path

PACKAGE = "skills/design-library"
CONFIG = "registry/design-library.json"


def verify_previous(package):
    pointer = package / "index.json"
    if not pointer.exists():
        return
    state = as_json(pointer)
    if state.get("schema_version") == 1:
        expected = {}
        for entry in state["entries"].values():
            expected.update(entry["files"])
        actual = {f"entries/{path}": value for path, value in inventory(package / "entries").items()}
    elif state.get("schema_version") == 2:
        snapshot = safe_path(package, state["snapshot"])
        expected = state["files"]
        actual = inventory(snapshot)
    else:
        raise ValueError("Unsupported installed snapshot")
    if actual != expected:
        raise ValueError("Consumer files have local changes. Review them before syncing.")


def sync(root, router_root, export, expected_sha):
    if not SHA.fullmatch(expected_sha):
        raise ValueError("Sync requires a complete source SHA")
    git = ["git", "-C", str(root)]
    sha = subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output([*git, "status", "--porcelain"], text=True).strip()
    if sha != expected_sha or dirty:
        raise ValueError("Source checkout must be clean and match --source-sha")
    config = as_json(safe_path(router_root, CONFIG))
    if config.get("schema_version") != 1 or config.get("repository") != export["repository"]:
        raise ValueError("Consumer configuration identity mismatch")
    selected = sorted({eid for project in config["projects"].values()
                       for stage in project["stages"].values() for eid in stage["entries"]})
    if not selected or set(selected) - set(export["entries"]):
        raise ValueError("Consumer requested an unknown or empty entry selection")
    package = safe_path(router_root, PACKAGE)
    if not (package / "SKILL.md").is_file():
        raise ValueError("Consumer adapter is missing")
    lock_path = subprocess.check_output(
        ["git", "-C", str(router_root), "rev-parse", "--git-path", "design-library-sync.lock"], text=True).strip()
    lock_path = Path(lock_path)
    if not lock_path.is_absolute():
        lock_path = router_root / lock_path
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        _sync_locked(root, package, export, sha, selected)


def _sync_locked(root, package, export, sha, selected):
    verify_previous(package)
    contents = {}
    for eid in selected:
        entry = export["entries"][eid]
        contents[f"manifests/{eid}.json"] = encode(entry)
        for path, expected in entry["files"].items():
            content = safe_path(root, f"entries/{eid}/{path}").read_bytes()
            if digest(content) != expected:
                raise ValueError(f"Source changed during sync: {eid}/{path}")
            contents[f"entries/{eid}/{path}"] = content
    files = {path: digest(content) for path, content in contents.items()}
    snapshot_id = f"{sha}-{digest(encode(selected))[:12]}"
    snapshot_name = f"snapshots/{snapshot_id}"
    snapshot = safe_path(package, snapshot_name)
    pointer = {"schema_version": 2, "repository": export["repository"], "commit_sha": sha,
               "snapshot": snapshot_name, "entries": selected, "files": files}
    # The active pointer is the commit point. Interrupted staging is never selected.
    with tempfile.TemporaryDirectory(prefix=".design-staging-", dir=package.parent) as directory:
        staging = Path(directory)
        staged = staging / "snapshot"
        for path, content in contents.items():
            file = staged / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(content)
        if inventory(staged) != files:
            raise ValueError("Staged snapshot failed validation")
        if snapshot.exists():
            if inventory(snapshot) != files:
                raise ValueError("Existing immutable snapshot differs")
        else:
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged, snapshot)
        next_pointer = staging / "index.json"
        next_pointer.write_bytes(encode(pointer))
        verify_previous(package)
        os.replace(next_pointer, package / "index.json")
