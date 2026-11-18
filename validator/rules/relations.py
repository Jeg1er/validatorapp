from decimal import Decimal, InvalidOperation
from ..models import Cell, Issue


def rule_j(tables, schemas, settings):
    sources = [table for table in tables if table.kind in {"items", "facts"} and not table.no_data and not table.parse_error]
    masters = [table for table in tables if table.kind == "masteritems" and not table.parse_error]
    valid_masters = [table for table in masters if table.headers.count("item_uid") == 1]
    if not sources:
        return []
    if not valid_masters:
        return [Issue("J", "ERROR", "Cannot check item_uid references: masteritems with an item_uid column is missing.",
                      table_ids=[table.id for table in sources + masters])]
    known = set()
    for table in valid_masters:
        column = table.headers.index("item_uid")
        known.update(row[column] for row in table.records[1:] if len(row) > column and row[column] != "")
    issues = []
    for table in sources:
        if table.headers.count("item_uid") != 1:
            issues.append(Issue("J", "ERROR", f"{table.filename}: one item_uid column is required for the reference check.",
                                table_ids=[table.id]))
            continue
        column = table.headers.index("item_uid")
        for row_number, row in enumerate(table.records[1:], 1):
            if column >= len(row):
                continue
            uid = row[column]
            if uid not in known:
                issues.append(Issue("J", "ERROR", f"{table.filename}: item_uid {uid!r} is absent from masteritems.",
                                    [Cell(table.id, row_number, column)], item_uid=uid))
    return issues


def rule_k(tables, schemas, settings):
    issues = []
    for table in tables:
        if table.kind != "dimensions" or table.no_data or table.parse_error:
            continue
        missing = [name for name in ("item_uid", "width", "height", "depth") if table.headers.count(name) != 1]
        if missing:
            issues.append(Issue("K", "ERROR", f"{table.filename}: cannot check dimensions without unique columns: {', '.join(missing)}.",
                                table_ids=[table.id]))
            continue
        dimensions = [(name, table.headers.index(name)) for name in ("width", "height", "depth")]
        uid_column = table.headers.index("item_uid")
        for row_number, row in enumerate(table.records[1:], 1):
            bad, names = [], []
            for name, column in dimensions:
                value = row[column] if column < len(row) else ""
                try:
                    zero = Decimal(value.replace(",", ".")) == 0 if value.strip() else True
                except InvalidOperation:
                    zero = False  # Non-numeric values are I errors, not K zero warnings.
                if zero:
                    bad.append(Cell(table.id, row_number, column))
                    names.append(name)
            if bad:
                uid = row[uid_column] if uid_column < len(row) else ""
                issues.append(Issue("K", "WARNING", f"{table.filename}: empty or zero dimensions: {', '.join(names)}.",
                                    bad, item_uid=uid))
    return issues
