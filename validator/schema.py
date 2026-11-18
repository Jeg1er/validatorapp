from .models import Cell, Field, Issue, Schema, Table
from .types import parse_type


def build_schemas(tables: list[Table], *, validate_types: bool = True) -> tuple[dict[str, Schema], list[Issue]]:
    """Read key definitions; lookup can skip type checks it does not use."""
    schemas, issues = {}, []
    ambiguous = set()
    for table in tables:
        if table.empty or table.parse_error:
            issues.append(Issue("KEY", "ERROR", f"Key file {table.filename} is empty or unreadable.",
                                table_ids=[table.id]))
            continue
        headers = [value.strip().casefold() for value in table.headers]
        if any(headers.count(name) != 1 for name in ("mandatory", "name", "type")):
            issues.append(Issue("KEY", "ERROR", f"{table.filename}: unique Mandatory, Name and Type headers are required.",
                                [Cell(table.id, 0, c) for c in range(len(headers))]))
            continue
        mi, ni, ti = (headers.index(name) for name in ("mandatory", "name", "type"))
        fields, names = [], set()
        invalid = False
        for ri, row in enumerate(table.records[1:], 1):
            if not any(value.strip() for value in row):
                continue
            if len(row) <= max(mi, ni, ti):
                issues.append(Issue("KEY", "ERROR", f"{table.filename}: incomplete schema row {ri + 1}.",
                                    [Cell(table.id, ri, c) for c in range(max(mi, ni, ti) + 1)]))
                invalid = True
                continue
            mandatory, name, type_name = row[mi].strip().casefold(), row[ni].strip(), row[ti].strip()
            if mandatory not in {"yes", "no"} or not name or name in names:
                issues.append(Issue("KEY", "ERROR", f"{table.filename}: invalid Mandatory/Name or duplicated schema name {name!r}.",
                                    [Cell(table.id, ri, mi), Cell(table.id, ri, ni)]))
                invalid = True
                continue
            if validate_types and parse_type(type_name).kind == "unknown":
                issues.append(Issue("KEY", "ERROR", f"{table.filename}: unsupported type {type_name!r} for {name}.",
                                    [Cell(table.id, ri, ti)]))
                invalid = True
            names.add(name)
            fields.append(Field(name, type_name, mandatory == "yes", Cell(table.id, ri, ni)))
        if not fields:
            invalid = True
            issues.append(Issue("KEY", "ERROR", f"{table.filename}: no field definitions.", table_ids=[table.id]))
        if table.kind in schemas or table.kind in ambiguous:
            schemas.pop(table.kind, None)
            ambiguous.add(table.kind)
            issues.append(Issue("KEY", "ERROR", f"More than one key file matches prefix {table.kind!r}; no schema selected.",
                                table_ids=[table.id]))
        elif not invalid:
            schemas[table.kind] = Schema(table.kind, table.id, fields)
    return schemas, issues
