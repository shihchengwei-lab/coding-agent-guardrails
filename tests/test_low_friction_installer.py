import json
from pathlib import Path

import pytest

from installer import guardrails_installer as installer


def test_detects_one_root_test_ecosystem_and_avoids_guessing(tmp_path, monkeypatch):
    monkeypatch.setattr(installer.shutil, "which", lambda name: f"/bin/{name}")
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    assert installer.detect_primary_check(tmp_path) == ["python", "-m", "pytest", "-q"]

    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"test": "vitest"}}), encoding="utf-8")
    assert installer.detect_primary_check(tmp_path) is None


def test_package_placeholder_is_not_a_test(tmp_path, monkeypatch):
    monkeypatch.setattr(installer.shutil, "which", lambda name: f"/bin/{name}")
    (tmp_path / "package.json").write_text(json.dumps({
        "scripts": {"test": "echo \"Error: no test specified\" && exit 1"}
    }), encoding="utf-8")
    assert installer.detect_primary_check(tmp_path) is None


@pytest.mark.parametrize(
    ("filename", "content", "expected"),
    [
        ("package.json", json.dumps({"scripts": {"test": "vitest"}}), ["npm", "test"]),
        ("Cargo.toml", "[package]\nname='demo'\nversion='0.1.0'\n", ["cargo", "test"]),
        ("go.mod", "module example.com/demo\n", ["go", "test", "./..."]),
        (
            "pubspec.yaml",
            "name: demo\ndependencies:\n  flutter:\n    sdk: flutter\n",
            ["flutter", "test"],
        ),
    ],
)
def test_detects_each_supported_single_ecosystem(
    tmp_path, filename, content, expected, monkeypatch,
):
    monkeypatch.setattr(installer.shutil, "which", lambda name: f"/bin/{name}")
    (tmp_path / filename).write_text(content, encoding="utf-8")
    assert installer.detect_primary_check(tmp_path) == expected


def test_detection_requires_the_ecosystem_executable(tmp_path, monkeypatch):
    (tmp_path / "Cargo.toml").write_text(
        "[package]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8"
    )
    monkeypatch.setattr(installer.shutil, "which", lambda name: None)
    assert installer.detect_primary_check(tmp_path) is None


def test_check_remove_cli_and_single_coordinator_hook_contract():
    parsed = installer.build_parser().parse_args(["check", "remove", "primary"])
    assert parsed.check_command == "remove"

    source = Path(installer.__file__).read_text(encoding="utf-8")
    assert "guardrails-coordinator" in source
    assert "slime-stop" not in source
    assert "agentcam-turn-end" not in source


def test_new_install_no_longer_manages_slime_markdown():
    assert ".slime/corridor.md" not in installer.MANAGED_RELATIVE_PATHS
    assert ".slime/PRUNED.md" not in installer.MANAGED_RELATIVE_PATHS
    source = Path(installer.__file__).read_text(encoding="utf-8")
    assert 'for name in ("corridor.md", "PRUNED.md")' not in source
