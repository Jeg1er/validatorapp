"""Change exchange settings here without changing the GUI."""
from dataclasses import dataclass

RULE_ORDER = ("A", "C", "D", "E", "F", "G", "I", "H", "J", "K", "B")


@dataclass(frozen=True)
class Settings:
    delimiter: str | None = None  # None = detect each CSV independently.
    input_encoding: str = "utf-8"
    sql_encoding: str | None = None  # Set from SQL Server collation: e.g. cp1251.
    sql_extra_forbidden: str = ""  # Only confirmed restrictions, not SQL syntax.
    allow_empty_values: bool = True  # Mandatory refers to column presence.
    max_file_bytes: int = 256 * 1024 * 1024
    max_archive_bytes: int = 768 * 1024 * 1024
