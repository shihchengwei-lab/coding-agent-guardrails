import unittest
from pathlib import Path

from bench.prepare import build_prompt


class PreparePromptTests(unittest.TestCase):
    def test_prompt_does_not_expose_scoring_guardrails(self):
        task = {
            "prompt": "Fix the bug.",
            "test_command": "python -m unittest",
            "allowed_files": ["app.py"],
            "max_changed_files": 1,
            "max_line_delta": 5,
        }

        prompt = build_prompt(task, "baseline", Path.cwd())

        self.assertIn("# Task", prompt)
        self.assertIn("Fix the bug.", prompt)
        self.assertIn("python -m unittest", prompt)
        self.assertNotIn("Scoring guardrails", prompt)
        self.assertNotIn("Allowed files", prompt)
        self.assertNotIn("Max changed files", prompt)
        self.assertNotIn("Max patch line delta", prompt)


if __name__ == "__main__":
    unittest.main()
