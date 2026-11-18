"""Conservative SQL-style type checks; original values remain strings."""
from __future__ import annotations
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation

INTEGER = re.compile(r"^[+-]?\d+$", re.ASCII)
NUMBER = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$", re.ASCII)
DECIMAL_COMMA = re.compile(r"^[+-]?\d+,\d+(?:[eE][+-]?\d+)?$", re.ASCII)


@dataclass(frozen=True)
class TypeSpec:
    kind: str
    raw: str
    base: str = ""
    length: int | None = None
    precision: int | None = None
    scale: int | None = None


def parse_type(text: str) -> TypeSpec:
    raw = text.strip().casefold()
    match = re.fullmatch(r"([a-z ]+)\s*(?:\(\s*(\d+|max)(?:\s*,\s*(\d+))?\s*\))?", raw)
    if not match:
        return TypeSpec("unknown", text)
    base = match[1].strip()
    a = int(match[2]) if match[2] and match[2] != "max" else None
    b = int(match[3]) if match[3] else None
    if base in {"varchar", "nvarchar", "char", "nchar", "text", "ntext", "string"}:
        return TypeSpec("text", text, base, length=a)
    if base in {"int", "integer", "bigint", "smallint", "tinyint"}:
        return TypeSpec("integer", text, base)
    if base in {"numeric", "decimal", "number", "float", "double", "double precision", "real", "money", "smallmoney"}:
        return TypeSpec("number", text, base, precision=a if base in {"numeric", "decimal"} else None,
                        scale=(b if b is not None else 0) if a is not None and base in {"numeric", "decimal"} else None)
    if base in {"boolean", "bool", "bit"}:
        return TypeSpec("boolean", text, base)
    if base == "date":
        return TypeSpec("date", text, base)
    if base in {"datetime", "datetime2", "smalldatetime", "datetimeoffset"}:
        return TypeSpec("datetime", text, base)
    if base == "time":
        return TypeSpec("time", text, base)
    if base in {"uuid", "uniqueidentifier"}:
        return TypeSpec("uuid", text, base)
    return TypeSpec("unknown", text, base)


def value_error(value: str, spec: TypeSpec, allow_empty=True, sql_encoding=None) -> str | None:
    if value == "":
        return None if allow_empty else "empty value"
    if spec.kind == "text":
        if spec.length is not None:
            if spec.base in {"nvarchar", "nchar", "ntext"}:
                length = len(value.encode("utf-16-le", errors="surrogatepass")) // 2
            elif sql_encoding:
                try:
                    length = len(value.encode(sql_encoding))
                except UnicodeEncodeError:
                    return "value is not representable in the SQL code page"
            else:
                length = len(value)
            if length > spec.length:
                return f"length {length} exceeds {spec.length}"
        return None
    if spec.kind == "integer":
        if not INTEGER.fullmatch(value):
            return "expected an integer"
        bounds = {"tinyint": (0, 255), "smallint": (-32768, 32767),
                  "int": (-2147483648, 2147483647), "integer": (-2147483648, 2147483647),
                  "bigint": (-9223372036854775808, 9223372036854775807)}
        try:
            number = int(value)
        except ValueError:
            return "integer is too long"
        low, high = bounds[spec.base]
        return None if low <= number <= high else "integer is outside the SQL type range"
    if spec.kind == "number":
        if not NUMBER.fullmatch(value):
            return "expected a finite number with a decimal point"
        try:
            number = Decimal(value)
            if not number.is_finite():
                return "number is not finite"
            if spec.precision is not None:
                scale = spec.scale or 0
                integer_digits = max(0, number.copy_abs().adjusted() + 1) if number else 0
                fractional_digits = max(0, -number.as_tuple().exponent)
                # Trailing fractional zeros do not require rounding or lose value.
                for digit in reversed(number.as_tuple().digits):
                    if digit == 0 and fractional_digits:
                        fractional_digits -= 1
                    else:
                        break
                if integer_digits > spec.precision - scale or fractional_digits > scale:
                    return f"value exceeds numeric({spec.precision},{scale}) without rounding"
        except (InvalidOperation, ValueError):
            return "invalid number"
        return None
    if spec.kind == "boolean":
        allowed = {"0", "1"} if spec.base == "bit" else {"0", "1", "true", "false"}
        return None if value.casefold() in allowed else "expected boolean / bit"
    try:
        if spec.kind == "date":
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value, re.ASCII):
                return "expected YYYY-MM-DD"
            date.fromisoformat(value)
        elif spec.kind == "datetime":
            if not re.match(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}", value, re.ASCII):
                return "expected an ISO date and time"
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if spec.base == "datetime" and parsed.year < 1753:
                return "SQL datetime cannot precede 1753"
        elif spec.kind == "time":
            time.fromisoformat(value)
        elif spec.kind == "uuid":
            uuid.UUID(value)
        else:
            return "unsupported declared type"
    except (ValueError, TypeError):
        return f"invalid {spec.kind}"
    return None
