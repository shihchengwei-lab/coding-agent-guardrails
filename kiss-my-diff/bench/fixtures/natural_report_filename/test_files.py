import unittest

from reports.files import report_filename


class ReportFilenameTests(unittest.TestCase):
    def test_simple_title(self):
        self.assertEqual(report_filename("Weekly Report"), "weekly-report.pdf")

    def test_punctuation_and_repeated_spaces(self):
        self.assertEqual(report_filename("  Sales: Q2 / Final  "), "sales-q2-final.pdf")


if __name__ == "__main__":
    unittest.main()
