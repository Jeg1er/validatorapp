"""Keep schema CSVs in the selected key ZIP before validation starts."""
from __future__ import annotations

import copy
import csv
import io
import os
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from .archive import ArchiveError, detect_delimiter
from .config import Settings


@dataclass
class KeyCleanupResult:
    removed: list[str] = field(default_factory=list)
    backup_path: Path | None = None


def _check_cancelled(cancelled):
    if cancelled():
        raise InterruptedError("Key ZIP cleanup cancelled.")


def _has_key_headers(raw: bytes, settings: Settings) -> bool:
    encoding = settings.input_encoding
    if raw.startswith(b"\xef\xbb\xbf"):
        encoding = "utf-8-sig"
    elif raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        encoding = "utf-16"
    try:
        text = raw.decode(encoding, errors="surrogateescape")
        reader = csv.reader(io.StringIO(text, newline=""), strict=True,
                            delimiter=settings.delimiter or detect_delimiter(text))
        for row in reader:
            if any(value.strip() for value in row):
                headers = [value.strip().casefold() for value in row]
                return headers == [
                    "mandatory",
                    "name",
                    "type",
                    "description",
                    "solution",
                    "comments",
                ]
    except (UnicodeError, csv.Error):
        pass
    return False


def _copy_stream(source, target, cancelled):
    while True:
        _check_cancelled(cancelled)
        chunk = source.read(1024 * 1024)
        if not chunk:
            break
        target.write(chunk)


def _backup(path: Path, cancelled) -> Path:
    backup_path = None
    try:
        with path.open("rb") as source, tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=path.name + ".backup-", suffix=".zip", delete=False
        ) as target:
            backup_path = Path(target.name)
            _copy_stream(source, target, cancelled)
            target.flush()
            os.fsync(target.fileno())
        return backup_path
    except BaseException:
        if backup_path is not None:
            backup_path.unlink(missing_ok=True)
        raise


def clean_key_archive(path: Path, settings: Settings, cancelled=lambda: False) -> KeyCleanupResult:
    """Filter the original ZIP atomically; preserve kept CSV bytes and a backup.

    Only the header decides eligibility. Invalid types or malformed data rows
    in a schema CSV remain available to the normal validator.
    """
    path = Path(path).resolve()
    temporary_path = None
    try:
        _check_cancelled(cancelled)
        csv.field_size_limit(settings.max_file_bytes)
        with zipfile.ZipFile(path) as source:
            kept, removed, total = [], [], 0
            for info in source.infolist():
                _check_cancelled(cancelled)
                if info.is_dir():
                    continue
                if PurePosixPath(info.filename.replace("\\", "/")).suffix.casefold() != ".csv":
                    removed.append(info.filename)
                    continue
                total += info.file_size
                if info.file_size > settings.max_file_bytes or total > settings.max_archive_bytes:
                    raise ArchiveError("The key ZIP exceeds the configured CSV size limit.")
                with source.open(info) as stream:
                    raw = stream.read(settings.max_file_bytes + 1)
                if len(raw) > settings.max_file_bytes:
                    raise ArchiveError(f"{info.filename} exceeds the configured file size limit.")
                if _has_key_headers(raw, settings):
                    kept.append(info)
                else:
                    removed.append(info.filename)
            if not removed:
                return KeyCleanupResult()

            with tempfile.NamedTemporaryFile(
                dir=path.parent, prefix="." + path.name + ".", suffix=".tmp", delete=False
            ) as temporary:
                temporary_path = Path(temporary.name)
            with zipfile.ZipFile(temporary_path, "w") as target:
                target.comment = source.comment
                for info in kept:
                    _check_cancelled(cancelled)
                    with source.open(info) as entry, target.open(copy.copy(info), "w") as output:
                        _copy_stream(entry, output, cancelled)
            _check_cancelled(cancelled)
            backup_path = _backup(path, cancelled)
        # All ZIP handles are closed before replacing the file on Windows.
        _check_cancelled(cancelled)
        os.replace(temporary_path, path)
        temporary_path = None
        return KeyCleanupResult(removed, backup_path)
    except InterruptedError:
        raise
    except (OSError, RuntimeError, zipfile.BadZipFile, NotImplementedError) as exc:
        raise ArchiveError(f"Cannot clean key ZIP: {exc}") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
