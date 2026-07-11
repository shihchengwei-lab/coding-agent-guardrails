from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_standalone_installers_leave_no_permanent_backups_or_duplicate_agents_writer():
    posix = read("slime-coding/install.sh")
    powershell = read("slime-coding/install-codex.ps1")

    assert ".bak-" not in posix
    assert ".bak-" not in powershell
    assert "Install-ManagedBlock" not in powershell
    assert 'Join-Path $Project "AGENTS.md"' not in powershell


def test_current_runtime_has_no_legacy_parsers():
    patch_cost = read("slime-coding/bin/patch-cost")
    corridor = read("corridor-ci/bin/corridor_ci.py")

    assert 'return "legacy"' not in patch_cost
    assert "SLIME_TEST_CMD" not in patch_cost
    assert "SLIME_TYPECHECK_CMD" not in patch_cost
    assert "Independent check )?Command" not in patch_cost
    assert "LEGACY_RECORDED_MARKER" not in corridor


def test_current_docs_describe_real_boundaries_without_stale_claims():
    root = read("README.md")
    root_zh = read("README.zh-TW.md")
    slime = read("slime-coding/README.md")
    handoff = read("corridor-ci/docs/HANDOFF_SPEC.md")

    assert "direct edits are checked before writing" in root
    assert "shell writes are checked immediately afterward" in root
    assert "OS sandbox" in root
    assert "寫入前" in root_zh and "寫入後" in root_zh and "OS sandbox" in root_zh
    assert "不會備份既有設定" in slime
    assert "changed-file limit" not in handoff
    assert "manual` or `unverified`,\n   manual, or unverified" not in root


def test_migration_guide_covers_every_breaking_transition():
    migration = read("docs/MIGRATION.md")

    assert "Agentcam 0.4 → 0.5" in migration
    assert "Corridor CI v12 → v13" in migration
    assert "inline command → trusted check" in migration
    assert "guardrails check set primary --" in migration
    assert "[locally recorded by agentcam]" in migration
