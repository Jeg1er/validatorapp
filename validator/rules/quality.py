"""Data-quality warnings that do not require a key archive."""
from decimal import Decimal, InvalidOperation

from ..models import Cell, Issue
from ..types import DECIMAL_COMMA, NUMBER


def rule_l(tables, schemas, settings):
    issues = []
    for table in tables:
        if table.parse_error or table.no_data:
            continue
        for cell, value in table.cells():
            text = value.strip()
            if not cell.row or not (NUMBER.fullmatch(text) or DECIMAL_COMMA.fullmatch(text)):
                continue
            try:
                negative = Decimal(text.replace(",", ".")) < 0
            except InvalidOperation:
                continue
            if negative:
                name = table.headers[cell.column] if cell.column < len(table.headers) else "extra column"
                issues.append(Issue("L", "WARNING", f"{table.filename}: negative value {value!r} in {name!r}.", [cell]))
    return issues


def rule_m(tables, schemas, settings):
    issues = []
    for table in tables:
        if table.kind != "facts" or table.parse_error or len(table.records) < 2:
            continue
        for prefix in ("sold", "stock"):
            columns = [column for column, name in enumerate(table.headers)
                       if name.casefold().startswith(prefix)]
            if not columns:
                continue
            total = (len(table.records) - 1) * len(columns)
            empty_count = sum(column >= len(row) or not row[column].strip()
                              for row in table.records[1:] for column in columns)
            if empty_count * 5 > total * 4:
                empty = [Cell(table.id, row_number, column)
                         for row_number, row in enumerate(table.records[1:], 1)
                         for column in columns if column >= len(row) or not row[column].strip()]
                percent = 100 * empty_count / total
                issues.append(Issue(
                    "M", "WARNING", f"{table.filename}: {prefix}* group has {len(empty)}/{total} "
                    f"empty values ({percent:.1f}%); more than 80% are empty.", empty,
                    "Columns: " + ", ".join(table.headers[column] for column in columns) +
                    ". Empty strings, whitespace and missing fields count as empty; zero does not."
                ))
    return issues


def rule_n(tables, schemas, settings):
    issues = []
    for table in tables:
        if table.parse_error or len(table.records) < 2:
            continue
        for column, name in enumerate(table.headers):
            if "uid" not in name.casefold():
                continue
            if all(column >= len(row) or not row[column].strip() for row in table.records[1:]):
                cells = [Cell(table.id, row, column) for row in range(len(table.records))]
                issues.append(Issue("N", "WARNING", f"{table.filename}: UID column {name!r} is entirely empty.", cells))
    return issues
