import csv
import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from validator.archive import file_kind, read_table
from validator.config import RULE_ORDER, Settings
from validator.engine import validate_archives
from validator.models import Cell, Field, Schema
from validator.rules.characters import rule_c, rule_d
from validator.types import parse_type, value_error


def csv_bytes(rows, delimiter=";", bom=False):
    stream = io.StringIO(newline="")
    csv.writer(stream, delimiter=delimiter).writerows(rows)
    return stream.getvalue().encode("utf-8-sig" if bom else "utf-8")


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def archive(self, name, files):
        path = self.root / name
        with zipfile.ZipFile(path, "w") as archive:
            for filename, value in files.items():
                archive.writestr(filename, value)
        return path

    def key(self, fields=None, kind="sample"):
        fields = fields or [["Yes", "uid", "varchar"], ["Yes", "qty", "integer"], ["No", "description", "varchar"]]
        return self.archive("key.zip", {f"docs/{kind}_rules.csv": csv_bytes([["Mandatory", "Name", "Type"]] + fields)})

    def validate(self, rows, fields=None, settings=None):
        data = self.archive("data.zip", {"sample_20261009.csv": csv_bytes(rows)})
        return validate_archives(data, self.key(fields), settings or Settings(sql_encoding="utf-8"))

    def test_order_and_valid_optional_omission(self):
        result = self.validate([["uid", "qty"], ["00123", "42"]])
        self.assertEqual(result.issues, [])
        self.assertEqual(tuple(result.completed_rules), RULE_ORDER)
        self.assertEqual(result.tables["data:0"].records[1][0], "00123")

    def test_optional_present_and_reordered_columns(self):
        result = self.validate([["description", "qty", "uid"], ["Text", "42", "00123"]])
        self.assertEqual(result.issues, [])

    def test_empty_archive_and_all_empty_files(self):
        for files in ({}, {"sample_a.csv": b"", "sample_b.csv": b"\n"}):
            result = validate_archives(self.archive("data.zip", files), self.key(), Settings(sql_encoding="utf-8"))
            self.assertEqual([i.rule for i in result.issues], ["A"])

    def test_partial_empty_file_b_last(self):
        files = {"sample_a.csv": csv_bytes([["uid", "qty"], ["1", "2"]]), "sample_b.csv": b""}
        result = validate_archives(self.archive("data.zip", files), self.key(), Settings(sql_encoding="utf-8"))
        self.assertEqual([i.rule for i in result.issues], ["B"])

    def test_c_control_unicode_and_literal_separators(self):
        bad = "\x00<>:\"/\\|?*%#&+;\u00a0\u00ad\u1680\u180e\u2000\u200d\u202f\u205f\u2060\u3000\ufeff"
        table = read_table(csv_bytes([["uid", "name"], ["1", bad]], bom=True), "sample_a.csv", "data:0", "data", Settings())
        issues = rule_c([table], {}, Settings())
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].cells, [Cell("data:0", 1, 1)])
        self.assertIn("U+0000", issues[0].text)
        self.assertIn("U+FEFF", issues[0].text)
        clean = read_table(csv_bytes([["uid", "name"], ["1", "Text"]], bom=True), "x_a.csv", "x", "data", Settings())
        self.assertEqual(rule_c([clean], {}, Settings()), [])

    def test_d_invalid_utf8_bytes_and_configured_codepage(self):
        table = read_table(b"uid;name\n1;\xff\n", "sample_a.csv", "d", "data", Settings())
        issues = rule_d([table], {}, Settings(sql_encoding="utf-8"))
        self.assertIn("0xFF", issues[0].text)
        emoji = read_table(csv_bytes([["uid", "name"], ["1", "🙂"]]), "sample_a.csv", "d", "data", Settings())
        self.assertEqual(len(rule_d([emoji], {}, Settings(sql_encoding="cp1251"))), 1)
        schema = Schema("sample", "key", [Field("name", "nvarchar", True, Cell("key", 1, 1))])
        self.assertEqual(rule_d([emoji], {"sample": schema}, Settings(sql_encoding="cp1251")), [])

    def test_d_unknown_is_reported_as_partial(self):
        result = self.validate([["uid", "qty"], ["1", "2"]], settings=Settings())
        self.assertEqual([i.rule for i in result.issues], ["D"])
        self.assertEqual(result.issues[0].severity, "WARNING")

    def test_e_decimal_comma_and_i_numeric(self):
        result = self.validate([["uid", "qty"], ["1", "2,5"]])
        self.assertEqual([i.rule for i in result.issues], ["E", "G", "I"])
        self.assertEqual(result.issues[0].cells, [Cell("data:0", 1, 1)])

    def test_f_header_count_h_missing_unknown(self):
        result = self.validate([["uid", "unknown", "another"], ["1", "2", "3"]])
        codes = [i.rule for i in result.issues]
        self.assertEqual(codes[0], "F")
        self.assertIn("H", codes)

    def test_g_missing_delimiter_marks_full_row(self):
        result = self.validate([["uid", "qty"], ["12342"]])
        issue = next(i for i in result.issues if i.rule == "G")
        self.assertEqual(issue.cells, [Cell("data:0", 1, 0), Cell("data:0", 1, 1)])

    def test_i_checks_names_after_reordering(self):
        result = self.validate([["qty", "uid"], ["text", "00123"]])
        issue = next(i for i in result.issues if i.rule == "I")
        self.assertEqual(issue.cells, [Cell("data:0", 1, 0)])

    def test_h_duplicate_headers(self):
        result = self.validate([["uid", "uid"], ["1", "2"]])
        self.assertTrue(any(i.rule == "H" and "duplicated" in i.text for i in result.issues))

    def test_j_and_k_cross_file_cells(self):
        files = {
            "masteritems_a.csv": csv_bytes([["item_uid"], ["001"]]),
            "items_a.csv": csv_bytes([["item_uid"], ["999"]]),
            "facts_a.csv": csv_bytes([["item_uid"], ["001"]]),
            "dimensions_a.csv": csv_bytes([["item_uid", "width", "height", "depth"], ["001", "0", "", "3"]]),
        }
        keys = {}
        for kind in ["masteritems", "items", "facts", "dimensions"]:
            fields = [["Yes", "item_uid", "varchar"]]
            if kind == "dimensions":
                fields += [["Yes", name, "numeric"] for name in ["width", "height", "depth"]]
            keys[f"{kind}_rules.csv"] = csv_bytes([["Mandatory", "Name", "Type"]] + fields)
        result = validate_archives(self.archive("data.zip", files), self.archive("key.zip", keys), Settings(sql_encoding="utf-8"))
        self.assertEqual([i.rule for i in result.issues], ["J", "K"])
        self.assertEqual(result.issues[0].item_uid, "999")
        self.assertEqual(len(result.issues[1].cells), 2)
        self.assertEqual(result.issues[1].severity, "WARNING")

    def test_matching_first_underscore_in_both_archives(self):
        self.assertEqual(file_kind("nested/items_client.csv"), "items")
        self.assertEqual(file_kind("docs/items_rules.csv"), "items")

    def test_ambiguous_or_missing_key_is_not_guessed(self):
        key = self.archive("key.zip", {"sample_a.csv": csv_bytes([["Mandatory", "Name", "Type"], ["Yes", "uid", "varchar"]]),
                                       "sample_b.csv": csv_bytes([["Mandatory", "Name", "Type"], ["Yes", "uid", "varchar"]])})
        data = self.archive("data.zip", {"sample_a.csv": csv_bytes([["uid"], ["1"]])})
        result = validate_archives(data, key, Settings(sql_encoding="utf-8"))
        self.assertTrue(any(i.rule == "KEY" for i in result.issues))
        self.assertTrue(any(i.rule == "F" for i in result.issues))

    def test_bad_zip_malformed_csv_and_bom(self):
        bad = self.root / "bad.zip"; bad.write_bytes(b"not ZIP")
        self.assertEqual(validate_archives(bad, None).issues[0].rule, "FILE")
        raw = b'uid;qty\n1;"unclosed\n'
        result = validate_archives(self.archive("data.zip", {"sample_a.csv": raw}), self.key(), Settings(sql_encoding="utf-8"))
        self.assertTrue(any(i.rule == "G" for i in result.issues))

    def test_decimal_quoted_comma_delimiter(self):
        raw = csv_bytes([["uid", "qty"], ["1", "2,5"]], delimiter=",")
        data = self.archive("data.zip", {"sample_a.csv": raw})
        result = validate_archives(data, self.key(), Settings(sql_encoding="utf-8"))
        self.assertEqual(result.tables["data:0"].delimiter, ",")
        self.assertTrue(any(i.rule == "E" for i in result.issues))

    def test_type_precision_date_and_range(self):
        self.assertIsNone(value_error("00123", parse_type("varchar")))
        self.assertIsNone(value_error("12.50", parse_type("numeric(5,2)")))
        self.assertIsNone(value_error("1.5000", parse_type("numeric(5,2)")))
        self.assertIsNotNone(value_error("1234.50", parse_type("numeric(5,2)")))
        self.assertIsNotNone(value_error("256", parse_type("tinyint")))
        self.assertIsNone(value_error("2026-10-09", parse_type("date")))
        self.assertIsNotNone(value_error("2026-02-31", parse_type("date")))

    def test_no_key_does_not_disable_independent_rules(self):
        data = self.archive("data.zip", {"sample_a.csv": csv_bytes([["uid", "qty"], ["1", "2,5"]])})
        result = validate_archives(data, None, Settings(sql_encoding="utf-8"))
        self.assertTrue(any(i.rule == "E" for i in result.issues))
        self.assertFalse(any(i.rule == "F" for i in result.issues))

    def test_archive_limit_and_cancellation(self):
        data = self.archive("data.zip", {"sample_a.csv": b"uid\n123\n"})
        result = validate_archives(data, self.key(), Settings(max_file_bytes=2))
        self.assertEqual(result.issues[0].rule, "FILE")
        result = validate_archives(data, self.key(), cancelled=lambda: True)
        self.assertTrue(result.cancelled)


if __name__ == "__main__":
    unittest.main()
