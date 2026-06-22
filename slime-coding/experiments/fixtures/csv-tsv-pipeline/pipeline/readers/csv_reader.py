"""CSV reader: parse a CSV file into a list of dicts (one per row)."""
import csv


def read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))
