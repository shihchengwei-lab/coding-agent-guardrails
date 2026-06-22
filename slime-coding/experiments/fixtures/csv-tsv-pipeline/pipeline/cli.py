"""Pipeline CLI: `convert` and `count`. Dispatches to a reader / writer pair."""
import argparse
import sys

from .readers import csv_reader
from .writers import json_writer


def cmd_convert(args):
    rows = csv_reader.read(args.input)
    json_writer.write(rows, args.output)
    return 0


def cmd_count(args):
    rows = csv_reader.read(args.input)
    print(len(rows))
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog="pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)

    conv = sub.add_parser("convert", help="convert input to JSON")
    conv.add_argument("--input", required=True)
    conv.add_argument("--output", required=True)
    conv.set_defaults(func=cmd_convert)

    cnt = sub.add_parser("count", help="print row count")
    cnt.add_argument("--input", required=True)
    cnt.set_defaults(func=cmd_count)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
