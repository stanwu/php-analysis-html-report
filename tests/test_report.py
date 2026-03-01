import json
import os
import tempfile
import unittest
from pathlib import Path

import codebase_analysis_html_report as r


class TestHelpers(unittest.TestCase):
    def test_norm_path(self) -> None:
        self.assertEqual(r._norm_path(r"foo\bar\baz.php"), "foo/bar/baz.php")
        self.assertEqual(r._norm_path("foo/bar"), "foo/bar")

    def test_dir_ancestors(self) -> None:
        self.assertEqual(r._dir_ancestors("a/b/c.txt"), ["", "a", "a/b"])
        self.assertEqual(r._dir_ancestors("single.txt"), [""])
        self.assertEqual(r._dir_ancestors("a.txt"), [""])

    def test_hist_empty(self) -> None:
        h = r._compute_equal_width_hist([], bins=5)
        self.assertEqual(h["min"], 0)
        self.assertEqual(h["max"], 0)
        self.assertEqual(h["bins"][0]["count"], 0)

    def test_hist_constant(self) -> None:
        h = r._compute_equal_width_hist([3, 3, 3], bins=10)
        self.assertEqual(h["min"], 3)
        self.assertEqual(h["max"], 3)
        self.assertEqual(h["bins"][0]["count"], 3)


class TestBuildReport(unittest.TestCase):
    def _write_json(self, path: Path, obj: dict) -> None:
        path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")

    def test_build_report_outputs_single_html(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            input_path = td_path / "analysis_report.json"
            output_path = td_path / "report.html"

            sample = {
                "summary": {
                    "total_files": 2,
                    "total_branches": 5,
                    "most_complex": [
                        {"file": "a.php", "max_depth": 2, "total_branches": 3},
                        {"file": "dir/b.php", "max_depth": 1, "total_branches": 2},
                    ],
                },
                "files": {
                    "a.php": {
                        "max_depth": 2,
                        "total_branches": 3,
                        "branches": [{"type": "if", "line": 1, "depth": 0, "condition": "x"}],
                        "functions": [],
                    },
                    "dir/b.php": {
                        "max_depth": 1,
                        "total_branches": 2,
                        "branches": [],
                        "functions": [],
                    },
                },
            }
            self._write_json(input_path, sample)

            r.build_report(
                input_path=input_path,
                output_path=output_path,
                top_n=10,
                max_details=1,
                bins=5,
            )

            self.assertTrue(output_path.exists())
            html = output_path.read_text(encoding="utf-8")

            self.assertIn("<!doctype html>", html.lower())
            self.assertIn('type="application/json" id="dataOverview"', html)
            self.assertIn('type="application/json" id="dataDirs"', html)
            self.assertIn('type="application/json" id="dataFiles"', html)
            self.assertIn('type="application/json" id="dataDetails"', html)

            # Ensure template placeholders are fully replaced.
            self.assertNotIn("{{DATA_OVERVIEW}}", html)
            self.assertNotIn("{{DATA_DIRS}}", html)
            self.assertNotIn("{{DATA_FILES}}", html)
            self.assertNotIn("{{DATA_DETAILS}}", html)

            # Verify embedded JSON is parseable.
            def extract_json(block_id: str) -> dict:
                start = html.index(f'id="{block_id}"')
                # Find the end of the opening tag, then the closing script.
                open_end = html.index(">", start) + 1
                close = html.index("</script>", open_end)
                return json.loads(html[open_end:close])

            ov = extract_json("dataOverview")
            self.assertEqual(ov["total_files"], 2)
            self.assertEqual(ov["total_branches"], 5)

            dirs = extract_json("dataDirs")
            self.assertIn("", dirs["nodes"])  # root dir node
            self.assertIn("dir", dirs["nodes"])
            self.assertIn("dir", dirs["children"][""])
            self.assertIn("files", dirs)
            self.assertEqual(dirs["files"][""], [0])
            self.assertEqual(dirs["files"]["dir"], [1])

            files = extract_json("dataFiles")["files"]
            self.assertEqual(len(files), 2)

            det = extract_json("dataDetails")["details"]
            # max_details=1 => exactly one file id has details.
            self.assertEqual(len(det), 1)

    def test_json_embedded_is_script_safe(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            input_path = td_path / "analysis_report.json"
            output_path = td_path / "report.html"

            sample = {
                "summary": {"total_files": 1, "total_branches": 1, "most_complex": []},
                "files": {
                    "x.php": {
                        "max_depth": 1,
                        "total_branches": 1,
                        "branches": [
                            {
                                "type": "if",
                                "line": 1,
                                "depth": 0,
                                "condition": "</script><script>alert(1)</script>",
                            }
                        ],
                        "functions": [],
                    }
                },
            }
            self._write_json(input_path, sample)
            r.build_report(input_path=input_path, output_path=output_path, top_n=5, max_details=1, bins=3)

            html = output_path.read_text(encoding="utf-8")
            # Should not contain a raw "</script>" inside JSON blocks due to escaping.
            self.assertNotIn("</script><script>alert(1)</script>", html)
            self.assertIn("<\\/", html)


if __name__ == "__main__":
    unittest.main()
