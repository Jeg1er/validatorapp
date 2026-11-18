"""CLI uses the same validation modules as the GUI; no Qt required."""
import argparse
import json
import sys
from pathlib import Path
from validator.config import Settings
from validator.engine import validate_archives


def main():
    parser = argparse.ArgumentParser(description="Validate a CSV exchange ZIP against a key ZIP.")
    parser.add_argument("archive", type=Path)
    parser.add_argument("--key", type=Path)
    parser.add_argument("--encoding", default="utf-8")
    parser.add_argument("--sql-encoding", default=None, help="Actual SQL Server code page, e.g. cp1251; omit if unknown.")
    parser.add_argument("--delimiter", choices=[";", ",", "tab", "|"], default=None)
    parser.add_argument("--json", action="store_true", help="Print structured results instead of text.")
    args = parser.parse_args()
    settings = Settings(input_encoding=args.encoding, sql_encoding=args.sql_encoding,
                        delimiter="\t" if args.delimiter == "tab" else args.delimiter)
    result = validate_archives(args.archive, args.key, settings)
    if args.json:
        payload = {"errors": result.error_count, "warnings": result.warning_count,
                   "completed_rules": result.completed_rules,
                   "issues": [{"rule": i.rule, "severity": i.severity, "text": i.text,
                               "details": i.details, "item_uid": i.item_uid,
                               "cells": [{"file": result.tables[c.table_id].filename,
                                          "record": c.row + 1, "column": c.column + 1,
                                          "line": result.tables[c.table_id].line_numbers[c.row] if
                                          c.row < len(result.tables[c.table_id].line_numbers) else None} for c in i.cells]}
                              for i in result.issues]}
        print(json.dumps(payload, ensure_ascii=True, indent=2))
    else:
        for issue in result.issues:
            text = f"{issue.severity} [{issue.rule}]: {issue.text}"
            if issue.item_uid:
                text += f"; item_uid={issue.item_uid}"
            print(text.encode(sys.stdout.encoding or "utf-8", errors="backslashreplace").decode(sys.stdout.encoding or "utf-8"))
        print(f"Errors: {result.error_count}; warnings: {result.warning_count}")
    return 1 if result.error_count else 0


if __name__ == "__main__":
    sys.exit(main())
