from __future__ import annotations

import re
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

from validator.archive import load_archive
from validator.config import Settings
from validator.schema import build_schemas


ID_COLUMN = re.compile(r"(?:id|uid|.+_(?:id|uid))", re.IGNORECASE)


class SearchErrors(ValueError):
    """Individual failures, not lines of a traceback or heading text."""

    def __init__(self, errors):
        self.errors = tuple(str(error) for error in errors)
        super().__init__("\n".join(self.errors))


@dataclass
class ConsolidatedData:
    headers: list[str]
    rows: list[list[str]]
    item_uids: list[str]
    record_count: int


def archive_signature(data_path: Path, key_path: Path):
    result = []
    for path in (data_path, key_path):
        path = Path(path).resolve()
        stat = path.stat()
        result.append((str(path), stat.st_size, stat.st_mtime_ns))
    return tuple(result)


class ProductIndex:
    """Search logic independent of PyQt6."""

    def __init__(self, data_path: Path, key_path: Path,
                 settings: Settings | None = None, cancelled=lambda: False,
                 progress=lambda text: None):
        settings = settings or Settings()

        progress("Reading data archive...")
        data_tables = load_archive(Path(data_path), "data", settings, cancelled)
        self._check_cancelled(cancelled)
        progress("Reading key archive...")
        key_tables = load_archive(Path(key_path), "key", settings, cancelled)
        self._check_cancelled(cancelled)
        progress("Checking key files...")
        # Links use declared column names, not the types used by validation.
        schemas, issues = build_schemas(key_tables, validate_types=False)
        errors = [issue.text for issue in issues if issue.severity == "ERROR"]
        if errors:
            raise SearchErrors(errors)

        self.tables = {}
        self.columns = {}
        self.id_columns = {}
        self.links = defaultdict(list)

        progress("Building links...")
        for table in data_tables:
            self._check_cancelled(cancelled)
            if table.parse_error:
                errors.append(f"{table.filename}: {table.parse_error}")
                continue
            if table.no_data:
                continue
            schema = schemas.get(table.kind)
            if schema is None:
                errors.append(f"{table.filename}: no valid matching key file.")
                continue
            if len(set(table.headers)) != len(table.headers):
                errors.append(f"{table.filename}: duplicate column names.")
                continue

            columns = {name: position for position, name in enumerate(table.headers)}
            declared_names = {field.name for field in schema.fields}
            identifier_columns = [
                position for name, position in columns.items()
                if name in declared_names and ID_COLUMN.fullmatch(name)
            ]
            self.tables[table.id] = table
            self.columns[table.id] = columns
            self.id_columns[table.id] = identifier_columns

            for row_number, row in enumerate(table.records[1:], 1):
                self._check_cancelled(cancelled)
                if len(row) != len(table.headers):
                    errors.append(
                        f"{table.filename}, record {row_number + 1}: expected "
                        f"{len(table.headers)} fields, found {len(row)}. "
                        "Fix the CSV structure before searching."
                    )
                    continue
                reference = (table.id, row_number)
                for column in identifier_columns:
                    value = row[column]
                    if value != "":
                        self.links[(table.headers[column], value)].append(reference)
        if errors:
            raise SearchErrors(errors)

    @staticmethod
    def _check_cancelled(cancelled):
        if cancelled():
            raise InterruptedError("Search cancelled.")

    def _tables_of_kind(self, kind):
        return [table for table in self.tables.values() if table.kind == kind]

    def _require_columns(self, table, required):
        columns = self.columns[table.id]
        missing = [name for name in required if name not in columns]
        if missing:
            raise SearchErrors([
                f"{table.filename}: missing columns: {', '.join(missing)}."
            ])
        return columns

    def _resolve_uids(self, mode, query):
        masters = self._tables_of_kind("masteritems")
        if not masters:
            raise SearchErrors(["The data archive has no non-empty masteritems file."])
        known_uids = set()
        for table in masters:
            columns = self._require_columns(table, ["item_uid"])
            uid_column = columns["item_uid"]
            if uid_column not in self.id_columns[table.id]:
                raise SearchErrors([
                    f"{table.filename}: item_uid must be declared in the matching key file."
                ])
            known_uids.update(row[uid_column] for row in table.records[1:]
                              if row[uid_column] != "")

        found = []
        if mode == "uid":
            if query in known_uids:
                found.append(query)
        elif mode == "name":
            for table in masters:
                columns = self._require_columns(table, ["item_uid", "name"])
                for row in table.records[1:]:
                    if row[columns["name"]].casefold() == query.casefold():
                        uid = row[columns["item_uid"]]
                        if uid:
                            found.append(uid)
        elif mode == "barcode":
            barcode_tables = self._tables_of_kind("barcodes")
            if not barcode_tables:
                raise SearchErrors(["The data archive has no non-empty barcodes file."])
            for table in barcode_tables:
                columns = self._require_columns(table, ["barcode", "item_uid"])
                for row in table.records[1:]:
                    if row[columns["barcode"]] == query:
                        uid = row[columns["item_uid"]]
                        if uid:
                            found.append(uid)
            missing = set(found) - known_uids
            if missing:
                raise SearchErrors([
                    f"barcodes references item_uid {uid!r}, which is absent from masteritems."
                    for uid in sorted(missing)
                ])
        else:
            raise SearchErrors([f"Unknown search mode: {mode!r}."])
        return list(dict.fromkeys(found))

    def search(self, mode, query, cancelled=lambda: False, progress=lambda text: None):
        query = query.strip()
        if not query:
            raise SearchErrors(["Enter a value to search for."])
        progress("Resolving item UID...")
        targets = self._resolve_uids(mode, query)
        if not targets:
            return ConsolidatedData(["File", "Column", "1"], [], [], 0)

        progress("Collecting records...")
        grouped_records = {}
        collected = set()
        for target_uid in targets:
            self._check_cancelled(cancelled)
            queue = deque()
            for table in self._tables_of_kind("masteritems"):
                uid_column = self.columns[table.id]["item_uid"]
                for row_number, row in enumerate(table.records[1:], 1):
                    if row[uid_column] == target_uid:
                        queue.append((table.id, row_number))
            visited = set()
            while queue:
                self._check_cancelled(cancelled)
                reference = queue.popleft()
                if reference in visited:
                    continue
                visited.add(reference)
                table_id, row_number = reference
                table = self.tables[table_id]
                row = table.records[row_number]
                uid_column = self.columns[table_id].get("item_uid")
                if uid_column is not None and row[uid_column] != target_uid:
                    continue
                if reference not in collected:
                    collected.add(reference)
                    grouped_records.setdefault(table_id, []).append(row_number)
                for column in self.id_columns[table_id]:
                    value = row[column]
                    if value != "":
                        queue.extend(self.links.get((table.headers[column], value), ()))

        progress("Preparing table...")
        width = max((len(rows) for rows in grouped_records.values()), default=1)
        headers = ["File", "Column"] + [str(number) for number in range(1, width + 1)]
        result_rows = []
        for table_id, row_numbers in grouped_records.items():
            self._check_cancelled(cancelled)
            table = self.tables[table_id]
            for column, name in enumerate(table.headers):
                values = [table.records[row_number][column] for row_number in row_numbers]
                result_rows.append([table.filename, name] + values + [""] * (width - len(values)))
        return ConsolidatedData(headers, result_rows, targets, len(collected))
