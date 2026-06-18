"""Baseline tests. Stdlib unittest so they run with either
`python3 -m pytest -q` or `python3 -m unittest` (no extra dependency)."""
import contextlib
import io
import tempfile
import unittest

from cli_notes.cli import main


def run(*argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        main(list(argv))
    return buf.getvalue()


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = self.tmp.name + "/n.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_and_list(self):
        run("--store", self.store, "add", "hello")
        run("--store", self.store, "add", "world")
        out = run("--store", self.store, "list")
        self.assertIn("hello", out)
        self.assertIn("world", out)
        # baseline contract: insertion order
        self.assertLess(out.index("hello"), out.index("world"))

    def test_list_empty(self):
        out = run("--store", self.store, "list")
        self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
