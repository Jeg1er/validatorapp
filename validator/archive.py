"""ZIP/CSV loading: keep original rows, values and physical line numbers."""
from __future__ import annotations
import csv
import io
import zipfile
from pathlib import Path, PurePosixPath

from .config import Settings
from .models import Table


class ArchiveError(ValueError):
    pass


def file_kind(filename: str) -> str:
    # User-confirmed matching: before the first underscore in BOTH archives.
    return PurePosixPath(filename.replace("\\", "/")).stem.split("_", 1)[0].casefold()


def detect_delimiter(text: str) -> str:
    # Trust the header before sampling records, which may have missing fields.
    candidates = ";,\t|"
    first_line = next((line for line in text.splitlines() if line.strip()), "")
    counts = {}
    for candidate in candidates:
        try:
            counts[candidate] = len(next(csv.reader([first_line], delimiter=candidate)))
        except (csv.Error, StopIteration):
            counts[candidate] = 1
    most = max(counts.values(), default=1)
    best = [candidate for candidate, count in counts.items() if count == most]
    if most > 1 and len(best) == 1:
        return best[0]
    try:
        return csv.Sniffer().sniff(text[:65536], delimiters=candidates).delimiter
    except csv.Error:
        return best[0] if most > 1 else ";"


def read_table(raw: bytes, name: str, table_id: str, source: str, settings: Settings) -> Table:
    csv.field_size_limit(settings.max_file_bytes)
    encoding = settings.input_encoding
    if raw.startswith(b"\xef\xbb\xbf"):
        encoding = "utf-8-sig"
    elif raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        encoding = "utf-16"
    try:
        text = raw.decode(encoding, errors="surrogateescape")
    except UnicodeError as exc:
        raise ArchiveError(f"Cannot decode {name} using {encoding}: {exc}") from exc
    # A file BOM is transport metadata. U+FEFF inside a cell is still checked.
    delimiter = settings.delimiter or detect_delimiter(text)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
    records, line_numbers = [], []
    parse_error = ""
    try:
        while True:
            start = reader.line_num + 1
            try:
                row = next(reader)
            except StopIteration:
                break
            # Keep blank data rows but ignore leading blank lines before header.
            if not records and not any(value.strip() for value in row):
                continue
            records.append(row)
            line_numbers.append(start)
    except csv.Error as exc:
        parse_error = f"CSV parsing failed near line {reader.line_num}: {exc}"
        # Preserve the entire file in a raw single-column table on parse failure.
        records = [["Raw CSV (parsing failed)"]] + [[line] for line in text.splitlines()]
        line_numbers = [0] + list(range(1, len(records)))
    return Table(table_id, name, file_kind(name), records, line_numbers,
                 delimiter, encoding, source, len(raw), parse_error)


def load_archive(path: Path, source: str, settings: Settings, cancelled=lambda: False) -> list[Table]:
    tables = []
    try:
        with zipfile.ZipFile(path) as archive:
            members = [info for info in archive.infolist() if not info.is_dir()]
            # Only conventional operating-system metadata is excluded.
            members = [info for info in members if not info.filename.startswith("__MACOSX/")
                       and PurePosixPath(info.filename).name not in {".DS_Store", "Thumbs.db"}]
            if sum(info.file_size for info in members) > settings.max_archive_bytes:
                raise ArchiveError("The archive exceeds the configured uncompressed size limit.")
            for index, info in enumerate(members):
                if cancelled():
                    break
                if info.file_size > settings.max_file_bytes:
                    raise ArchiveError(f"{info.filename} exceeds the configured file size limit.")
                with archive.open(info) as stream:
                    raw = stream.read(settings.max_file_bytes + 1)
                if len(raw) > settings.max_file_bytes:
                    raise ArchiveError(f"{info.filename} exceeds the configured file size limit.")
                tables.append(read_table(raw, info.filename, f"{source}:{index}", source, settings))
    except (OSError, RuntimeError, zipfile.BadZipFile, NotImplementedError) as exc:
        raise ArchiveError(f"Cannot read {source} ZIP: {exc}") from exc
    return tables
