"""Phase 1 tests: the project skeleton exists and imports."""
import importlib
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestSkeleton(unittest.TestCase):
    def test_packages_import(self):
        for name in ("source_parser", "query_language", "evaluator"):
            importlib.import_module(name)

    def test_required_directories_exist(self):
        for d in ("source_parser", "query_language", "evaluator",
                  "queries", "examples", "test_cases", "tests"):
            self.assertTrue(os.path.isdir(os.path.join(ROOT, d)), d)

    def test_requirements_lists_sly(self):
        with open(os.path.join(ROOT, "requirements.txt")) as f:
            self.assertIn("sly", f.read())


if __name__ == "__main__":
    unittest.main()
