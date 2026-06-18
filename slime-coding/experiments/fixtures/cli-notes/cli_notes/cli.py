"""Notes CLI: `add` and `list`. Insertion order is the baseline behaviour."""
import argparse
import sys

from . import store


def cmd_add(args):
    note = store.add(args.text, args.store)
    print(f'added note {note["id"]}')
    return 0


def cmd_list(args):
    for note in store.load(args.store):
        print(f'{note["id"]}\t{note["text"]}')
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog="notes")
    p.add_argument("--store", default=None, help="path to the notes JSON file")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="add a note")
    a.add_argument("text")
    a.set_defaults(func=cmd_add)

    lst = sub.add_parser("list", help="list notes")
    lst.set_defaults(func=cmd_list)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
