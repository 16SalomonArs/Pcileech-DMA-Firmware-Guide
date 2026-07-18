import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


class DocumentationTests(unittest.TestCase):
    def test_markdown_relative_links_exist(self):
        pattern = re.compile(r"\[[^]]+\]\(([^)#]+)")
        for markdown_path in REPO_ROOT.rglob("*.md"):
            for line_number, line in enumerate(markdown_path.read_text(encoding="utf-8").splitlines(), start=1):
                for match in pattern.finditer(line):
                    link = match.group(1)
                    if re.match(r"^(?:https?|mailto):", link):
                        continue
                    target = (markdown_path.parent / link).resolve()
                    self.assertTrue(
                        target.exists(),
                        f"{markdown_path.relative_to(REPO_ROOT)}:{line_number}: invalid relative link {link} -> {target}",
                    )

    def test_referenced_tool_paths_exist(self):
        expected_tools = (
            "coe-tools/check_cfgspace_coe.py",
            "coe-tools/make_cfgspace_coe.py",
            "coe-tools/make_writemask_coe.py",
            "coe-tools/make_zero4k_coe.py",
        )
        for relative_path in expected_tools:
            self.assertTrue(
                (REPO_ROOT / relative_path).is_file(),
                f"missing tool path: {relative_path}",
            )
        tool_pattern = re.compile(r"(?:\.\\)?coe-tools[\\/][A-Za-z0-9_.\\/-]+\.py")
        for markdown_path in REPO_ROOT.rglob("*.md"):
            text = markdown_path.read_text(encoding="utf-8")
            for match in tool_pattern.finditer(text):
                relative_path = match.group(0).removeprefix(".\\").replace("\\", "/")
                self.assertTrue(
                    (REPO_ROOT / relative_path).is_file(),
                    f"{markdown_path.relative_to(REPO_ROOT)}: invalid tool path {match.group(0)}",
                )

    def test_example_csvs_have_expected_columns(self):
        examples = {
            "coe-tools/examples/config_structure_test.csv": ("offset", "dword"),
            "coe-tools/examples/bar0_dwords.csv": ("offset", "dword"),
            "coe-tools/examples/writemask_structure_test.csv": ("offset", "mask"),
        }
        for relative_path, columns in examples.items():
            path = REPO_ROOT / relative_path
            self.assertTrue(path.is_file(), f"missing example CSV: {relative_path}")
            header = path.read_text(encoding="ascii").splitlines()[0].split(",")
            self.assertEqual(tuple(header), columns, f"invalid CSV header in {relative_path}")

    def test_documentation_entries(self):
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        firmware_guide = (REPO_ROOT / "FIRMWARE_GUIDE.md").read_text(encoding="utf-8")
        self.assertIn("## Table of Contents", readme, "README.md is missing the tutorial contents")
        self.assertIn("[README.md](README.md)", firmware_guide, "FIRMWARE_GUIDE.md is missing the README.md entry")
        self.assertTrue((REPO_ROOT / "README.md").is_file(), "missing README.md target")

    def test_support_files_are_linked_from_readme(self):
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        for directory in ("firmware-notes", "coe-tools"):
            for path in (REPO_ROOT / directory).rglob("*"):
                if not path.is_file():
                    continue
                relative_path = path.relative_to(REPO_ROOT).as_posix()
                self.assertIn(
                    f"]({relative_path})",
                    readme,
                    f"README.md is missing a contextual link to {relative_path}",
                )


if __name__ == "__main__":
    unittest.main()
