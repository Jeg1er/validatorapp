import re
import unicodedata

from ..models import Issue
from ..types import DECIMAL_COMMA, parse_type

# Structural CSV quotes/delimiters/record line endings are not cell values.
FORBIDDEN = re.compile(r'[\x00-\x1F<>:"/\\|?*%#&+;\u00A0\u00AD\u1680\u180E\u2000-\u200D\u202F\u205F\u2060\u3000\uFEFF]')


def char_description(char):
    number = ord(char)
    if 0xDC80 <= number <= 0xDCFF:
        return f"undecodable byte 0x{number - 0xDC00:02X}"
    return f"U+{number:04X} ({unicodedata.name(char, 'CONTROL / UNNAMED')})"


def rule_c(tables, schemas, settings):
    issues = []
    for table in tables:
        if table.parse_error:
            continue
        for cell, value in table.cells():
            bad = sorted(set(FORBIDDEN.findall(value)))
            if bad:
                codes = ", ".join(char_description(char) for char in bad)
                issues.append(Issue("C", "ERROR", f"{table.filename}: forbidden exchange character(s): {codes}.",
                                    [cell], "Character positions (1-based): " +
                                    ", ".join(str(i + 1) for i, char in enumerate(value) if FORBIDDEN.fullmatch(char))))
    return issues


def rule_d(tables, schemas, settings):
    issues = []
    if settings.sql_encoding is None:
        issues.append(Issue("D", "WARNING", "SQL Server code page is not configured; the SQL character check is partial.",
                            details="Invalid decoded bytes / Unicode and explicitly configured restrictions are checked. "
                                    "Set Settings.sql_encoding from the actual SQL Server collation to check varchar representability."))
    for table in tables:
        schema = schemas.get(table.kind)
        unicode_columns = set()
        if schema:
            unicode_names = {field.name for field in schema.fields if parse_type(field.type_name).base in {"nvarchar", "nchar", "ntext"}}
            unicode_columns = {i for i, name in enumerate(table.headers) if name in unicode_names}
        for cell, value in table.cells():
            bad = set()
            for char in set(value):
                if 0xD800 <= ord(char) <= 0xDFFF or char in settings.sql_extra_forbidden:
                    bad.add(char)
                elif settings.sql_encoding and not (cell.row and cell.column in unicode_columns):
                    try:
                        char.encode(settings.sql_encoding, errors="strict")
                    except UnicodeEncodeError:
                        bad.add(char)
            if bad:
                codes = ", ".join(char_description(char) for char in sorted(bad))
                issues.append(Issue("D", "ERROR", f"{table.filename}: SQL/input encoding incompatibility: {codes}.",
                                    [cell], f"Input encoding: {table.encoding}; SQL encoding: {settings.sql_encoding or 'not configured'}"))
    return issues


def rule_e(tables, schemas, settings):
    issues = []
    for table in tables:
        if table.parse_error:
            continue
        for cell, value in table.cells():
            if cell.row and DECIMAL_COMMA.fullmatch(value):
                issues.append(Issue("E", "ERROR", f"{table.filename}: decimal comma {value!r}; use a decimal point.", [cell]))
    return issues
