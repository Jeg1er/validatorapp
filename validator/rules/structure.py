from collections import Counter
from ..models import Cell, Issue
from ..types import parse_type, value_error


def header_cells(table):
    return [Cell(table.id, 0, column) for column in range(max(1, len(table.headers)))]


def rule_f(tables, schemas, settings):
    issues = []
    for table in tables:
        if table.parse_error or table.empty:
            continue
        schema = schemas.get(table.kind)
        if schema is None:
            issues.append(Issue("F", "ERROR", f"{table.filename}: no valid matching key schema for prefix {table.kind!r}.",
                                header_cells(table)))
            continue
        required = {field.name for field in schema.fields if field.required}
        selected_optional = {field.name for field in schema.fields if not field.required and field.name in table.headers}
        expected = len(required) + len(selected_optional)
        if len(table.headers) != expected:
            issues.append(Issue("F", "ERROR", f"{table.filename}: {len(table.headers)} headers; expected {expected} "
                                "(required columns plus optional columns actually supplied).", header_cells(table),
                                table_ids=[table.id, schema.table_id]))
    return issues


def rule_g(tables, schemas, settings):
    issues = []
    for table in tables:
        if table.parse_error:
            issues.append(Issue("G", "ERROR", f"{table.filename}: malformed CSV.",
                                [Cell(table.id, row, 0) for row in range(1, len(table.records))], table.parse_error))
            continue
        schema = schemas.get(table.kind)
        if schema is None:
            continue
        by_name = {field.name: parse_type(field.type_name) for field in schema.fields}
        for row_number, row in enumerate(table.records[1:], 1):
            if not row:  # Blank records inside a nonempty CSV are malformed rows.
                row = []
            cells = [Cell(table.id, row_number, column) for column in range(max(len(table.headers), len(row), 1))]
            if len(row) != len(table.headers):
                issues.append(Issue("G", "ERROR", f"{table.filename}: record {row_number + 1} has {len(row)} fields; "
                                    f"header has {len(table.headers)}. Check missing/extra delimiters.", cells))
                continue
            failed = [name for column, name in enumerate(table.headers) if name in by_name and
                      value_error(row[column], by_name[name], settings.allow_empty_values, settings.sql_encoding)]
            if failed:
                issues.append(Issue("G", "ERROR", f"{table.filename}: record {row_number + 1} does not match the declared type sequence.",
                                    cells, "Check the delimiter and values. A type mismatch alone does not prove a missing delimiter. "
                                    "Mismatched columns: " + ", ".join(failed)))
    return issues


def rule_i(tables, schemas, settings):
    issues = []
    for table in tables:
        if table.parse_error:
            continue
        schema = schemas.get(table.kind)
        if schema is None:
            continue
        fields = {field.name: field for field in schema.fields}
        for column, name in enumerate(table.headers):
            if name not in fields:
                continue
            spec = parse_type(fields[name].type_name)
            for row_number, row in enumerate(table.records[1:], 1):
                if column >= len(row):
                    continue  # G covers missing cells from malformed records.
                reason = value_error(row[column], spec, settings.allow_empty_values, settings.sql_encoding)
                if reason:
                    issues.append(Issue("I", "ERROR", f"{table.filename}: {name} expects {fields[name].type_name}; {reason}.",
                                        [Cell(table.id, row_number, column)],
                                        f"Value: {row[column]!r}; declared type: {fields[name].type_name}"))
    return issues


def rule_h(tables, schemas, settings):
    issues = []
    for table in tables:
        if table.empty or table.parse_error or table.kind not in schemas:
            continue
        schema = schemas[table.kind]
        allowed = {field.name for field in schema.fields}
        missing = [field for field in schema.fields if field.required and field.name not in table.headers]
        for field in missing:
            issues.append(Issue("H", "ERROR", f"{table.filename}: required column {field.name!r} is missing.",
                                header_cells(table) + [field.key_cell], table_ids=[table.id, schema.table_id]))
        counts = Counter(table.headers)
        for column, name in enumerate(table.headers):
            if name not in allowed or counts[name] > 1:
                reason = "unknown column name" if name not in allowed else "duplicated column name"
                issues.append(Issue("H", "ERROR", f"{table.filename}: {reason} {name!r}.", [Cell(table.id, 0, column)]))
    return issues
