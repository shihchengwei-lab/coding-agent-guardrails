# slime-coding (plugin development)

This repo IS the Slime Coding Claude Code plugin. It is not a Dart app — the
hooks here target *consuming* projects.

Layout: `.claude-plugin/plugin.json` (manifest), `hooks/hooks.json` (wiring),
`bin/` (hook executables), `skills/`, `commands/`, `templates/`.

When changing a hook executable in `bin/`, keep it dependency-free (stdlib
Python 3 only), never crash the user's session (exit 0 silently on unexpected
input), and remember: L2 gates may block on git facts only; L3 only reports.
Run `python3 -c 'import ast; ast.parse(open("bin/patch-cost").read())'` to
syntax-check after edits, and keep the `bin/` scripts executable (`chmod +x`).

The plugin's own discipline is described in `README.md`; the discipline block
that consumers paste lives in `templates/CLAUDE.slime.md`.
