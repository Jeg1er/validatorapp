from __future__ import annotations
from pathlib import Path

from .archive import ArchiveError, load_archive
from .config import RULE_ORDER, Settings
from .key_cleanup import clean_key_archive
from .models import Issue, ValidationResult
from .schema import build_schemas
from .rules.basic import rule_a, rule_b
from .rules.characters import rule_c, rule_d, rule_e
from .rules.structure import rule_f, rule_g, rule_h, rule_i
from .rules.relations import rule_j, rule_k
from .rules.quality import rule_l, rule_m, rule_n

RULES = dict(zip(RULE_ORDER, (rule_a, rule_c, rule_d, rule_e, rule_f, rule_g,
                            rule_i, rule_h, rule_j, rule_k, rule_l, rule_m, rule_n, rule_b)))


def validate_archives(data_path: Path, key_path: Path | None, settings: Settings | None = None,
                      progress=lambda text: None, cancelled=lambda: False) -> ValidationResult:
    settings = settings or Settings()
    result = ValidationResult()
    progress("Reading validation ZIP…")
    try:
        if key_path is not None and Path(data_path).is_file() and Path(key_path).is_file() and Path(data_path).samefile(key_path):
            raise ArchiveError("The validation ZIP and key ZIP must be different files.")
        tables = load_archive(Path(data_path), "data", settings, cancelled)
    except ArchiveError as exc:
        result.issues.append(Issue("FILE", "ERROR", str(exc)))
        return result
    result.tables.update((table.id, table) for table in tables)
    schemas, key_issues = {}, []
    if key_path is not None:
        progress("Reading key ZIP…")
        try:
            cleanup = clean_key_archive(Path(key_path), settings, cancelled)
            if cleanup.removed:
                key_issues.append(Issue("KEY", "INFO", f"Key ZIP cleaned: removed {len(cleanup.removed)} file(s).",
                                        details="Removed files:\n" + "\n".join(cleanup.removed) +
                                        f"\nBackup: {cleanup.backup_path}"))
            progress("Reading key ZIP…")
            key_tables = load_archive(Path(key_path), "key", settings, cancelled)
            result.tables.update((table.id, table) for table in key_tables)
            schemas, schema_issues = build_schemas(key_tables)
            key_issues.extend(schema_issues)
            if not key_tables:
                key_issues.append(Issue("KEY", "ERROR", "The key archive is empty."))
        except ArchiveError as exc:
            key_issues.append(Issue("KEY", "ERROR", str(exc)))
        except InterruptedError:
            result.cancelled = True
            return result           
    else:
        key_issues.append(Issue("KEY", "WARNING", "No key ZIP provided; F/G/I/H schema checks are skipped."))
    for code in RULE_ORDER:
        if cancelled():
            result.cancelled = True
            break
        progress(f"Validation rule {code}…")
        if code == "F":
            # Report invalid key before checks depending on it, preserving A–K order.
            result.issues.extend(key_issues)
        if key_path is None and code in {"F", "G", "I", "H"}:
            continue
        result.issues.extend(RULES[code](tables, schemas, settings))
        result.completed_rules.append(code)
    return result
