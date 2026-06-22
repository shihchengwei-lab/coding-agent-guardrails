# csv-tsv-pipeline (fixture)

A small Python pipeline that converts a CSV input to JSON. Multi-module
package: `pipeline/cli.py` + `pipeline/readers/csv_reader.py` +
`pipeline/writers/json_writer.py` + tests. Two CLI subcommands today:
`convert` and `count`.

The shape of the package (a `readers/` subpackage, a `writers/` subpackage)
is the architectural room a follow-up format-extensibility task can either
respect minimally (add one more file under `readers/`) or balloon into a
plugin / registry / base-class hierarchy. This is the design the cli-notes
fixture deliberately doesn't have.

Run: `python3 -m pytest -q`
