import json
from pathlib import Path

import benchmark_runner as runner


def test_prepare_run_keeps_hidden_tests_out_of_agent_workspace(tmp_path):
    lab = tmp_path / "lab"
    task_dir = lab / "tasks" / "demo"
    (task_dir / "base" / "tests").mkdir(parents=True)
    (task_dir / "hidden").mkdir()
    (task_dir / "base" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (task_dir / "hidden" / "test_hidden.py").write_text(
        "def test_hidden():\n    assert True\n",
        encoding="utf-8",
    )
    manifest = {
        "id": "demo",
        "prompt": "Fix it.",
        "public_command": "python -m pytest -q",
        "hidden_command": "python -m pytest -q",
        "max_files": 1,
        "max_line_delta": 8,
        "quality_checks": [],
    }

    run_dir = runner.prepare_run(
        task=manifest,
        lab_dir=lab,
        run_root=tmp_path / "runs",
        model="gpt-test",
        variant="baseline",
        force=False,
    )

    assert (run_dir / "work" / "app.py").exists()
    assert not (run_dir / "work" / "hidden").exists()
    assert "Fix it." in (run_dir / "PROMPT.md").read_text(encoding="utf-8")


def test_prepare_run_ignores_python_cache_files(tmp_path):
    lab = tmp_path / "lab"
    task_dir = lab / "tasks" / "demo"
    (task_dir / "base" / "__pycache__").mkdir(parents=True)
    (task_dir / "hidden").mkdir()
    (task_dir / "base" / "__pycache__" / "app.cpython-312.pyc").write_bytes(b"cache")
    (task_dir / "base" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    manifest = {
        "id": "demo",
        "prompt": "Fix it.",
        "public_command": "python -m pytest -q",
        "hidden_command": "python -m pytest -q",
        "max_files": 1,
        "max_line_delta": 8,
        "quality_checks": [],
    }

    run_dir = runner.prepare_run(
        task=manifest,
        lab_dir=lab,
        run_root=tmp_path / "runs",
        model="gpt-test",
        variant="baseline",
        force=False,
    )

    assert not (run_dir / "work" / "__pycache__").exists()


def test_prepare_kiss_run_adds_agent_file(tmp_path):
    lab = tmp_path / "lab"
    task_dir = lab / "tasks" / "demo"
    (task_dir / "base").mkdir(parents=True)
    (task_dir / "hidden").mkdir()
    (task_dir / "base" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (lab / "AGENT.md").write_text("Stop when done.\n", encoding="utf-8")
    manifest = {
        "id": "demo",
        "prompt": "Fix it.",
        "public_command": "python -m pytest -q",
        "hidden_command": "python -m pytest -q",
        "max_files": 1,
        "max_line_delta": 8,
        "quality_checks": [],
    }

    run_dir = runner.prepare_run(
        task=manifest,
        lab_dir=lab,
        run_root=tmp_path / "runs",
        model="gpt-test",
        variant="kiss",
        force=False,
    )

    assert (run_dir / "work" / "AGENT.md").read_text(encoding="utf-8") == "Stop when done.\n"
    assert "Follow the local AGENT.md" in (run_dir / "PROMPT.md").read_text(encoding="utf-8")


def test_prepare_discipline_run_uses_toolkit_block(tmp_path):
    root = tmp_path / "repo"
    lab = root / "kiss-my-diff" / "benchmark"
    task_dir = lab / "tasks" / "demo"
    (task_dir / "base").mkdir(parents=True)
    (task_dir / "hidden").mkdir()
    (task_dir / "base" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "templates").mkdir(parents=True)
    (root / "templates" / "DISCIPLINE.md").write_text(
        "## Coding Discipline\nfused block\n", encoding="utf-8"
    )
    manifest = {
        "id": "demo",
        "prompt": "Fix it.",
        "public_command": "python -m pytest -q",
        "hidden_command": "python -m pytest -q",
        "max_files": 1,
        "max_line_delta": 8,
        "quality_checks": [],
    }

    run_dir = runner.prepare_run(
        task=manifest,
        lab_dir=lab,
        run_root=tmp_path / "runs",
        model="gpt-test",
        variant="discipline",
        force=False,
    )

    agent_text = (run_dir / "work" / "AGENT.md").read_text(encoding="utf-8")
    assert agent_text == "## Coding Discipline\nfused block\n"
    assert "Follow the local AGENT.md" in (run_dir / "PROMPT.md").read_text(encoding="utf-8")


def test_prepare_kiss_run_can_use_repo_root_agent_file(tmp_path):
    repo = tmp_path / "repo"
    lab = repo / "benchmark"
    task_dir = lab / "tasks" / "demo"
    (task_dir / "base").mkdir(parents=True)
    (task_dir / "hidden").mkdir()
    (task_dir / "base" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / "AGENT.md").write_text("Stop when done.\n", encoding="utf-8")
    manifest = {
        "id": "demo",
        "prompt": "Fix it.",
        "public_command": "python -m pytest -q",
        "hidden_command": "python -m pytest -q",
        "max_files": 1,
        "max_line_delta": 8,
        "quality_checks": [],
    }

    run_dir = runner.prepare_run(
        task=manifest,
        lab_dir=lab,
        run_root=tmp_path / "runs",
        model="gpt-test",
        variant="kiss",
        force=False,
    )

    assert (run_dir / "work" / "AGENT.md").read_text(encoding="utf-8") == "Stop when done.\n"


def test_prepare_kiss_one_line_run_adds_minimal_agent_file(tmp_path):
    lab = tmp_path / "lab"
    task_dir = lab / "tasks" / "demo"
    (task_dir / "base").mkdir(parents=True)
    (task_dir / "hidden").mkdir()
    (task_dir / "base" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (lab / "AGENT.md").write_text("Stop when done.\n", encoding="utf-8")
    manifest = {
        "id": "demo",
        "prompt": "Fix it.",
        "public_command": "python -m pytest -q",
        "hidden_command": "python -m pytest -q",
        "max_files": 1,
        "max_line_delta": 8,
        "quality_checks": [],
    }

    run_dir = runner.prepare_run(
        task=manifest,
        lab_dir=lab,
        run_root=tmp_path / "runs",
        model="gpt-test",
        variant="kiss_one_line",
        force=False,
    )

    assert (
        run_dir / "work" / "AGENT.md"
    ).read_text(encoding="utf-8") == "Follow the KISS principle (Keep It Simple, Stupid).\n"
    assert "Follow the local AGENT.md" in (run_dir / "PROMPT.md").read_text(encoding="utf-8")


def test_prepare_experimental_kiss_variants_add_agent_file(tmp_path):
    lab = tmp_path / "lab"
    task_dir = lab / "tasks" / "demo"
    (task_dir / "base").mkdir(parents=True)
    (task_dir / "hidden").mkdir()
    (task_dir / "base" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    manifest = {
        "id": "demo",
        "prompt": "Fix it.",
        "public_command": "python -m pytest -q",
        "hidden_command": "python -m pytest -q",
        "max_files": 1,
        "max_line_delta": 8,
        "quality_checks": [],
    }

    expected = {
        "kiss_contrast_core": "do not guess APIs, helpers, or patterns.",
        "kiss_weighted_core": "Optimize for the smallest correct diff.",
        "kiss_weighted_contrast_core": "do not stop on an unverified change.",
    }

    for variant, marker in expected.items():
        run_dir = runner.prepare_run(
            task=manifest,
            lab_dir=lab,
            run_root=tmp_path / "runs",
            model="gpt-test",
            variant=variant,
            force=False,
        )

        agent_text = (run_dir / "work" / "AGENT.md").read_text(encoding="utf-8")
        assert marker in agent_text
        assert agent_text.endswith("\n")
        assert "Follow the local AGENT.md" in (run_dir / "PROMPT.md").read_text(encoding="utf-8")


def test_write_summary_reports_capability_and_discipline_separately(tmp_path):
    rows = [
        {
            "model": "gpt-5.5",
            "variant": "baseline",
            "task_id": "demo",
            "capability": 100.0,
            "discipline": 80.0,
            "total": 94.0,
        },
        {
            "model": "gpt-5.5",
            "variant": "kiss",
            "task_id": "demo",
            "capability": 100.0,
            "discipline": 100.0,
            "total": 100.0,
        },
    ]

    output = tmp_path / "summary.md"
    runner.write_summary(rows, output)

    text = output.read_text(encoding="utf-8")
    assert "| model | variant | runs | capability | discipline | total |" in text
    assert "| gpt-5.5 | baseline | 1 | 100.00 | 80.00 | 94.00 |" in text


def test_write_calibration_reports_pass_for_ordered_baseline_capability(tmp_path):
    rows = [
        {"model": "gpt-5.5", "variant": "baseline", "capability": 94.0},
        {"model": "gpt-5.4", "variant": "baseline", "capability": 92.0},
        {"model": "gpt-5.4-mini", "variant": "baseline", "capability": 89.0},
        {"model": "gpt-5.3-codex-spark", "variant": "baseline", "capability": 85.0},
        {"model": "gpt-5.3-codex-spark", "variant": "kiss", "capability": 99.0},
    ]

    output = tmp_path / "calibration.md"
    runner.write_calibration(rows, output)

    text = output.read_text(encoding="utf-8")
    assert "status: pass" in text
    assert "| model | baseline capability |" in text
    assert "| gpt-5.5 | 94.00 |" in text
    assert "| gpt-5.3-codex-spark | 85.00 |" in text
    assert "kiss" not in text


def test_write_calibration_reports_failure_when_weak_model_wins(tmp_path):
    rows = [
        {"model": "gpt-5.5", "variant": "baseline", "capability": 90.0},
        {"model": "gpt-5.4-mini", "variant": "baseline", "capability": 80.0},
        {"model": "gpt-5.3-codex-spark", "variant": "baseline", "capability": 91.0},
    ]

    output = tmp_path / "calibration.md"
    runner.write_calibration(rows, output)

    text = output.read_text(encoding="utf-8")
    assert "status: fail" in text
    assert "spark baseline is above mini" in text
    assert "spark baseline is above frontier" in text


def test_write_calibration_reports_saturated_capability(tmp_path):
    rows = [
        {"model": "gpt-5.5", "variant": "baseline", "capability": 100.0},
        {"model": "gpt-5.4", "variant": "baseline", "capability": 100.0},
        {"model": "gpt-5.4-mini", "variant": "baseline", "capability": 100.0},
        {"model": "gpt-5.3-codex-spark", "variant": "baseline", "capability": 100.0},
    ]

    output = tmp_path / "calibration.md"
    runner.write_calibration(rows, output)

    text = output.read_text(encoding="utf-8")
    assert "status: pass" in text
    assert "note: baseline capability is saturated" in text


def test_codex_command_prefers_windows_cmd_shim(monkeypatch):
    calls = []

    def fake_which(name):
        calls.append(name)
        if name == "codex.cmd":
            return "C:/Users/example/codex.cmd"
        return None

    monkeypatch.setattr(runner.shutil, "which", fake_which)

    assert runner.codex_command()[0] == "C:/Users/example/codex.cmd"
    assert calls[0] == "codex.cmd"


def test_verification_tree_restores_original_tests(tmp_path):
    lab = tmp_path / "lab"
    base = lab / "tasks" / "demo" / "base"
    hidden = lab / "tasks" / "demo" / "hidden"
    work = tmp_path / "work"
    (base / "tests").mkdir(parents=True)
    hidden.mkdir(parents=True)
    (work / "tests").mkdir(parents=True)
    (base / "tests" / "test_public.py").write_text("ORIGINAL = True\n", encoding="utf-8")
    (hidden / "tests").mkdir()
    (hidden / "tests" / "test_hidden.py").write_text("HIDDEN = True\n", encoding="utf-8")
    (work / "tests" / "test_public.py").write_text("ORIGINAL = False\n", encoding="utf-8")
    (work / "tests" / "test_extra.py").write_text("EXTRA = True\n", encoding="utf-8")

    with runner.verification_tree({"id": "demo"}, lab, work, include_hidden=True) as verify_dir:
        restored = (verify_dir / "tests" / "test_public.py").read_text(encoding="utf-8")
        assert restored == "ORIGINAL = True\n"
        assert (verify_dir / "tests" / "test_hidden.py").exists()
        assert not (verify_dir / "tests" / "test_extra.py").exists()
