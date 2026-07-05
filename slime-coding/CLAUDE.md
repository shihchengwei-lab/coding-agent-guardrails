# slime-coding (development)

This repo IS the Slime Coding tooling. It is not a Dart app — the hooks here
target *consuming* projects. It is installed by cloning and running
`install.sh` against a target project (no plugin / marketplace).

Layout: `install.sh` (wires a target project), `hooks/hooks.template.json`
(hook block with the `__SLIME_HOME__` placeholder), `bin/` (hook executables),
`skills/`, `commands/`, `templates/`.

When changing a hook executable in `bin/`, keep it dependency-free (stdlib
Python 3 only), never crash the user's session (exit 0 silently on unexpected
input), and remember: L2 gates may block on git facts only; L3 only reports.
Run `python3 -c 'import ast; ast.parse(open("bin/patch-cost").read())'` to
syntax-check after edits, and keep the `bin/` scripts executable (`chmod +x`).

After changing `hooks/hooks.template.json` or `install.sh`, sanity-check the
merge with `bash install.sh /tmp/throwaway-project` and confirm it is
idempotent and quotes the baked path.

The tool's own discipline is described in `README.md`; the discipline block
that consumers paste lives in `templates/CLAUDE.slime.md`.
