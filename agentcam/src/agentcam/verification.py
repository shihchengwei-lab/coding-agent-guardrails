"""Atomic verification records shared by CLI, hooks, handoff, and export."""
from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any


def new_record_id() -> str:
    return uuid.uuid4().hex


def write_record(parent: Path, record: dict[str, Any]) -> Path:
    record_id = str(record.get("record_id") or new_record_id())
    record = {**record, "record_id": record_id}
    directory = parent / "verifications"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{record_id}.json"
    temporary = directory / f".{record_id}.{os.getpid()}.tmp"
    temporary.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
    os.replace(temporary, target)
    return target


def read_records(parent: Path, embedded: list[Any] | None = None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = [
        value for value in (embedded or []) if isinstance(value, dict)
    ]
    seen = {
        str(record.get("record_id"))
        for record in records
        if record.get("record_id")
    }
    directory = parent / "verifications"
    try:
        paths = sorted(directory.glob("*.json"))
    except OSError:
        paths = []
    for path in paths:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(value, dict):
            continue
        record_id = str(value.get("record_id") or "")
        if record_id and record_id in seen:
            continue
        if record_id:
            seen.add(record_id)
        records.append(value)
    embedded_count = len(embedded or [])
    records[embedded_count:] = sorted(
        records[embedded_count:],
        key=lambda record: (
            str(record.get("recorded_at") or ""),
            str(record.get("record_id") or ""),
        ),
    )
    return records


def sync_manifest(parent: Path, timeout_seconds: float = 10.0) -> list[dict[str, Any]]:
    """Merge record files into manifest.json under a cross-process mkdir lock."""
    lock = parent / ".verification-lock"
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            lock.mkdir()
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise TimeoutError("timed out waiting for verification manifest lock")
            time.sleep(0.01)
    try:
        manifest_path = parent / "manifest.json"
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        evidence = data.get("evidence")
        if not isinstance(evidence, dict):
            raise ValueError("manifest evidence is malformed")
        embedded = evidence.get("verifications")
        if embedded is not None and not isinstance(embedded, list):
            raise ValueError("manifest verifications are malformed")
        records = read_records(parent, embedded)
        evidence["verifications"] = records
        temporary = manifest_path.with_name(
            f".{manifest_path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        )
        temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(temporary, manifest_path)
        return records
    finally:
        try:
            lock.rmdir()
        except OSError:
            pass


def transfer_records(source: Path, destination: Path) -> None:
    source_dir = source / "verifications"
    if not source_dir.is_dir():
        return
    destination_dir = destination / "verifications"
    destination_dir.mkdir(parents=True, exist_ok=True)
    for path in source_dir.glob("*.json"):
        target = destination_dir / path.name
        if not target.exists():
            shutil.copy2(path, target)
