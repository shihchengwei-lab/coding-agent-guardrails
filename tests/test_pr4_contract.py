from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_only_unified_installer_entrypoints_remain():
    assert (ROOT / "install.sh").is_file()
    assert (ROOT / "install.ps1").is_file()
    assert not (ROOT / "slime-coding" / "install.sh").exists()
    assert not (ROOT / "slime-coding" / "install-codex.ps1").exists()


def test_runtime_and_action_use_low_friction_contract():
    runtime = read("slime-coding/bin/patch-cost")
    action = read("corridor-ci/action.yml")
    installer = read("installer/guardrails_installer.py")

    assert ".guardrails/review.json" in runtime
    assert "guardrails internal scope set" in runtime
    assert "review_artifact" in action
    assert "agentcam_evidence" not in action
    assert "guardrails-coordinator" in installer


def test_obsolete_user_workflow_assets_are_pruned():
    for relative in (
        "slime-coding/bin/prune-inject",
        "slime-coding/commands/slime-corridor.md",
        "slime-coding/commands/slime-prune.md",
        "slime-coding/skills/slime-navigate/SKILL.md",
        "slime-coding/templates/.slime/corridor.md",
        "slime-coding/templates/.slime/PRUNED.md",
        "corridor-ci/examples/PULL_REQUEST_TEMPLATE.md",
        "corridor-ci/docs/assets/corridor-ci-before-after.svg",
    ):
        assert not (ROOT / relative).exists(), relative


def test_runtime_has_no_legacy_corridor_fallback_parser():
    runtime = read("slime-coding/bin/patch-cost")
    for token in (
        "RIGOR_LEVELS",
        "corridor_problem",
        "corridor_sections",
        "stop_blocks",
        "PRUNED.md",
        ".slime/corridor.md",
    ):
        assert token not in runtime


def test_current_docs_describe_real_hook_boundary():
    root = read("README.md")
    root_zh = read("README.zh-TW.md")
    assert "Direct edits are" in root and "checked before writing" in root
    assert "Shell writes can only be detected immediately after" in root
    assert "OS sandbox" in root
    assert "寫入前" in root_zh and "寫入後" in root_zh and "OS 權限" in root_zh


def test_user_docs_do_not_restore_removed_daily_steps():
    root = read("README.md")
    root_zh = read("README.zh-TW.md")
    corridor = read("corridor-ci/README.md")

    assert "You do not edit a corridor" in root
    assert "不必執行 Agentcam 指令" in root_zh
    assert "does not parse the pull-request body" in corridor
    assert "agentcam verify --" not in root
    assert "agentcam handoff" not in root
    assert "agentcam export latest" not in root


def test_root_docs_keep_the_author_disclosure_visible():
    root = read("README.md")
    root_zh = read("README.zh-TW.md")
    root_words = " ".join(root.split())

    assert "## Why a Vibe-Built Tool Needs Guardrails" in root
    assert "I am not a software engineer" in root_words
    assert "I vibed together a tool for limiting vibe coding" in root_words
    assert "## \u70ba\u4ec0\u9ebc\u6703\u6709\u4e00\u5957\u9650\u5236 vibe \u7684\u5de5\u5177" in root_zh
    assert "\u6211\u4e0d\u662f\u8edf\u9ad4\u5de5\u7a0b\u5e2b" in root_zh
    assert "vibe \u51fa\u4e86\u4e00\u5957\u9650\u5236 vibe \u7684\u5de5\u5177" in root_zh
