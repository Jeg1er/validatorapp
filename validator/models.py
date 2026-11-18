from __future__ import annotations
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Cell:
    table_id: str
    row: int  # 0 = original CSV header, 1 = first data record.
    column: int


@dataclass
class Table:
    id: str
    filename: str
    kind: str
    records: list[list[str]]
    line_numbers: list[int]
    delimiter: str
    encoding: str
    source: str = "data"
    size_bytes: int = 0
    parse_error: str = ""

    @property
    def headers(self):
        return self.records[0] if self.records else []

    @property
    def empty(self):
        return not any(value.strip() for row in self.records for value in row)

    @property
    def no_data(self):
        return self.empty or not any(value.strip() for row in self.records[1:] for value in row)

    def cells(self):
        for row, values in enumerate(self.records):
            for column, value in enumerate(values):
                yield Cell(self.id, row, column), value


@dataclass(frozen=True)
class Field:
    name: str
    type_name: str
    required: bool
    key_cell: Cell


@dataclass
class Schema:
    kind: str
    table_id: str
    fields: list[Field]


@dataclass
class Issue:
    rule: str
    severity: str
    text: str
    cells: list[Cell] = field(default_factory=list)
    details: str = ""
    item_uid: str = ""
    table_ids: list[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    tables: dict[str, Table] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)
    completed_rules: list[str] = field(default_factory=list)
    cancelled: bool = False

    @property
    def error_count(self):
        return sum(issue.severity == "ERROR" for issue in self.issues)

    @property
    def warning_count(self):
        return sum(issue.severity == "WARNING" for issue in self.issues)
