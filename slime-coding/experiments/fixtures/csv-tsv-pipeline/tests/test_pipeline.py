"""Integration tests for the pipeline CLI. Run: `python3 -m pytest -q` or
`python3 -m unittest` (no extra dependency)."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.cli import main


@contextlib.contextmanager
def captured_stdout():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        yield buf


def run(*argv):
    with captured_stdout() as buf:
        main(list(argv))
    return buf.getvalue()


class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _csv(self, content):
        p = self.dir / "input.csv"
        p.write_text(content, encoding="utf-8")
        return str(p)

    def _out_path(self):
        return str(self.dir / "output.json")

    def test_convert_csv_to_json(self):
        inp = self._csv("name,age\nalice,30\nbob,25\n")
        out = self._out_path()
        main(["convert", "--input", inp, "--output", out])
        with open(out, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["name"], "alice")
        self.assertEqual(data[1]["age"], "25")

    def test_count_csv_rows(self):
        inp = self._csv("name,age\nalice,30\nbob,25\ncarol,40\n")
        out = run("count", "--input", inp).strip()
        self.assertEqual(out, "3")


if __name__ == "__main__":
    unittest.main()
