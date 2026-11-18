from ..models import Issue


def rule_a(tables, schemas, settings):
    if not tables or all(table.no_data and not table.parse_error for table in tables):
        return [Issue("A", "ERROR", "The validation archive is empty or contains no data records.",
                      table_ids=[table.id for table in tables])]
    return []


def rule_b(tables, schemas, settings):
    if not tables or all(table.no_data and not table.parse_error for table in tables):
        return []  # A covers an entirely empty archive.
    return [Issue("B", "WARNING", f"{table.filename}: file is empty or contains only headers.",
                  table_ids=[table.id]) for table in tables if table.no_data and not table.parse_error]
