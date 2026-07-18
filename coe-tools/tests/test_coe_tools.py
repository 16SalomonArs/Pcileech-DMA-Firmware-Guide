import csv
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


TOOLS_PATH = Path(__file__).resolve().parents[1]
EXAMPLES_PATH = TOOLS_PATH / "examples"
sys.path.insert(0, str(TOOLS_PATH))

import check_cfgspace_coe
import make_cfgspace_coe
import make_writemask_coe
import make_zero4k_coe


def write_csv(path, rows):
    with path.open("w", encoding="ascii", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(("offset", "dword"))
        writer.writerows(rows)


def write_dwords(path, dwords):
    make_cfgspace_coe.write_coe(path, dwords)


def make_valid_dwords():
    dwords = ["00000000"] * 1024
    dwords[0x034 // 4] = "00000040"
    dwords[0x040 // 4] = "00000001"
    dwords[0x100 // 4] = "00030001"
    return dwords


class CoeToolTests(unittest.TestCase):
    def test_bare_dword_is_hex_not_decimal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "config.csv"
            coe_path = root / "config.coe"
            write_csv(csv_path, (("0x000", "00000010"),))
            dwords = make_cfgspace_coe.build_dwords(csv_path)
            make_cfgspace_coe.write_coe(coe_path, dwords)
            self.assertEqual(dwords[0], "00000010")
            self.assertEqual(check_cfgspace_coe.load_dwords(coe_path)[0], "00000010")

    def test_zero4k_uses_hex_and_rejects_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "bar.csv"
            write_csv(csv_path, (("0x000", "ABCDEF01"), ("0xFFC", "00000010")))
            dwords = make_zero4k_coe.build_dwords(csv_path)
            self.assertEqual(dwords[0], "ABCDEF01")
            self.assertEqual(dwords[-1], "00000010")
            write_csv(root / "unaligned.csv", (("0x002", "00000001"),))
            with self.assertRaisesRegex(ValueError, "DWORD-aligned"):
                make_zero4k_coe.build_dwords(root / "unaligned.csv")
            write_csv(root / "outside.csv", (("0x1000", "00000001"),))
            with self.assertRaisesRegex(ValueError, "DWORD-aligned"):
                make_zero4k_coe.build_dwords(root / "outside.csv")

    def test_config_builder_rejects_duplicate_and_wide_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_csv(root / "duplicate.csv", (("0x000", "00000001"), ("000", "00000002")))
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                make_cfgspace_coe.build_dwords(root / "duplicate.csv")
            write_csv(root / "wide.csv", (("0x000", "100000000"),))
            with self.assertRaisesRegex(ValueError, "32-bit"):
                make_cfgspace_coe.build_dwords(root / "wide.csv")

    def assert_checker_error(self, dwords, message):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.coe"
            write_dwords(path, dwords)
            with self.assertRaisesRegex(ValueError, message):
                check_cfgspace_coe.check_coe(path)

    def test_valid_capability_chain(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.coe"
            write_dwords(path, make_valid_dwords())
            _, standard, extended = check_cfgspace_coe.check_coe(path)
            self.assertEqual(standard, [(0x40, 0x01, 0x00)])
            self.assertEqual(extended, [(0x100, 0x0001, 0x3, 0x000)])

    def test_structure_fixture_matches_checker_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.coe"
            dwords = make_cfgspace_coe.build_dwords(EXAMPLES_PATH / "config_structure_test.csv")
            write_dwords(path, dwords)
            _, standard, extended = check_cfgspace_coe.check_coe(path)
            self.assertEqual(standard, [(0x40, 0x01, 0x00)])
            self.assertEqual(extended, [(0x100, 0x0001, 0x3, 0x000)])
            output = io.StringIO()
            with redirect_stdout(output):
                check_cfgspace_coe.main([str(path)])
            self.assertIn("EXT 0x100: id=0x0001 version=3 next=0x000", output.getvalue())

    def test_writemask_csv_only_opens_listed_bits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "writemask.csv"
            csv_path.write_text("offset,mask\n0x004,00000007\n0x03C,000000FF\n", encoding="ascii")
            dwords = make_writemask_coe.build_masks(csv_path)
            self.assertEqual(dwords[0x004 // 4], "00000007")
            self.assertEqual(dwords[0x03C // 4], "000000FF")
            self.assertEqual(dwords[0x000 // 4], "00000000")
            self.assertEqual(dwords[0x008 // 4], "00000000")
            self.assertEqual(dwords[0x040 // 4], "00000000")

    def test_writemask_csv_rejects_bad_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = (
                ("offset,mask\n0x002,00000001\n", "DWORD-aligned"),
                ("offset,mask\n0x1000,00000001\n", "DWORD-aligned"),
                ("offset,mask\n0x004,00000001\n0x004,00000002\n", "Duplicate"),
                ("offset,mask\n0x004,FFFF\n", "8-digit 32-bit"),
                ("offset,mask\n0x004,100000000\n", "8-digit 32-bit"),
            )
            for index, (contents, message) in enumerate(cases):
                csv_path = root / f"case-{index}.csv"
                csv_path.write_text(contents, encoding="ascii")
                with self.assertRaisesRegex(ValueError, message):
                    make_writemask_coe.build_masks(csv_path)

    def test_empty_capability_nodes_are_reported(self):
        dwords = make_valid_dwords()
        dwords[0x040 // 4] = "00000000"
        self.assert_checker_error(dwords, "Empty standard capability node")
        dwords = make_valid_dwords()
        dwords[0x100 // 4] = "20000001"
        dwords[0x200 // 4] = "00000000"
        self.assert_checker_error(dwords, "Empty extended capability node")

    def test_standard_loop_out_of_range_and_unaligned_pointer(self):
        dwords = make_valid_dwords()
        dwords[0x040 // 4] = "00004401"
        dwords[0x044 // 4] = "00004401"
        self.assert_checker_error(dwords, "Standard capability loop")
        dwords = make_valid_dwords()
        dwords[0x034 // 4] = "00000020"
        self.assert_checker_error(dwords, "(?i)standard capability pointer out of range")
        dwords = make_valid_dwords()
        dwords[0x034 // 4] = "00000042"
        self.assert_checker_error(dwords, "(?i)standard capability pointer unaligned")

    def test_extended_loop_out_of_range_and_unaligned_pointer(self):
        dwords = make_valid_dwords()
        dwords[0x100 // 4] = "20000001"
        dwords[0x200 // 4] = "20000001"
        self.assert_checker_error(dwords, "Extended capability loop")
        dwords = make_valid_dwords()
        dwords[0x100 // 4] = "08000001"
        self.assert_checker_error(dwords, "(?i)extended capability pointer out of range")
        dwords = make_valid_dwords()
        dwords[0x100 // 4] = "10100001"
        self.assert_checker_error(dwords, "(?i)extended capability pointer unaligned")

    def test_invalid_next_pointers_are_reported(self):
        dwords = make_valid_dwords()
        dwords[0x040 // 4] = "00002001"
        self.assert_checker_error(dwords, "(?i)standard capability pointer out of range in 0x40")
        dwords = make_valid_dwords()
        dwords[0x100 // 4] = "08030001"
        self.assert_checker_error(dwords, "(?i)extended capability pointer out of range in 0x100")


if __name__ == "__main__":
    unittest.main()
