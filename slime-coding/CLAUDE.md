# slime-coding (development)

This directory IS the Slime coordinator tooling. It is not a Dart app —
`bin/patch-cost` targets *consuming* projects. It is installed into a target
repository by the monorepo root installer (`install.sh` / `install.ps1` at the
repo root, which delegates to `installer/guardrails_installer.py`); there is
no per-directory installer here.

Layout: `bin/patch-cost` (the single hook coordinator and internal CLI),
`tests/` (unittest + shell contract tests), `docs/` (concept and design
notes), `benchmark/` (recorded benchmark tables and raw cells).

`patch-cost` depends on the sibling `agentcam` package: the root installer
pip-installs agentcam into the managed venv, and Stop hard-blocks if agentcam
fails to initialize. Running the tests locally therefore needs
`PYTHONPATH=../agentcam/src`:

```bash
PYTHONPATH=../agentcam/src python3 -m unittest discover -s tests
PYTHONPATH=../agentcam/src bash tests/test.sh
```

When changing `bin/patch-cost`: never crash the user's session (exit 0
silently on unexpected input); L2 gates may block on git facts only, L3 only
reports; keep `is_dependency_manifest` aligned with Corridor CI's
`DEPENDENCY_GLOBS` (a mismatch makes local artifacts underreport risk and the
PR gate reject them). Syntax-check after edits with
`python3 -c 'import ast; ast.parse(open("bin/patch-cost", encoding="utf-8").read())'`
(the explicit encoding matters on non-UTF-8 locale machines), and keep the
script executable (`chmod +x`).

The discipline block consumers get is the monorepo root
`templates/DISCIPLINE.md`, written into their CLAUDE.md and AGENTS.md by the
root installer.
