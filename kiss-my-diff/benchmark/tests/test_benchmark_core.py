from pathlib import Path

import benchmark_core as core


def test_score_keeps_capability_separate_from_discipline():
    result = core.RawResult(
        public_passed=True,
        hidden_passed=False,
        changed_files=["app/settings.py"],
        line_delta=3,
        dependency_incidents=0,
        quality_hits=2,
        quality_total=2,
    )

    score = core.score_result(result, max_files=1, max_line_delta=8)

    assert score.capability == 35.0
    assert score.discipline == 100.0
    assert score.total == 54.5


def test_new_dependency_is_an_incident(tmp_path):
    before = tmp_path / "before"
    after = tmp_path / "after"
    before.mkdir()
    after.mkdir()
    (before / "requirements.txt").write_text("requests==2.31.0\n", encoding="utf-8")
    (after / "requirements.txt").write_text(
        "requests==2.31.0\npython-slugify==8.0.4\n",
        encoding="utf-8",
    )

    assert core.dependency_incidents(before, after, ["requirements.txt"]) == 1


def test_baseline_calibration_rejects_weak_model_beating_strong_models():
    summary = {
        "gpt-5.5": 81.0,
        "gpt-5.4": 80.0,
        "gpt-5.4-mini": 79.0,
        "gpt-5.3-codex-spark": 90.0,
    }

    verdict = core.calibration_verdict(summary)

    assert not verdict.ok
    assert "spark baseline is above mini" in verdict.reasons
    assert "spark baseline is above frontier" in verdict.reasons


def test_baseline_calibration_accepts_monotone_capability_order():
    summary = {
        "gpt-5.5": 91.0,
        "gpt-5.4": 89.0,
        "gpt-5.4-mini": 78.0,
        "gpt-5.3-codex-spark": 65.0,
    }

    verdict = core.calibration_verdict(summary)

    assert verdict.ok
    assert verdict.reasons == []


def test_diff_stats_tracks_changed_files_and_line_delta(tmp_path):
    before = tmp_path / "before"
    after = tmp_path / "after"
    before.mkdir()
    after.mkdir()
    (before / "module.py").write_text("a = 1\nb = 2\n", encoding="utf-8")
    (after / "module.py").write_text("a = 1\nb = 3\nc = 4\n", encoding="utf-8")

    stats = core.diff_stats(before, after)

    assert stats.changed_files == ["module.py"]
    assert stats.line_delta == 3


def test_diff_stats_can_ignore_injected_agent_file(tmp_path):
    before = tmp_path / "before"
    after = tmp_path / "after"
    before.mkdir()
    after.mkdir()
    (before / "module.py").write_text("a = 1\n", encoding="utf-8")
    (after / "module.py").write_text("a = 2\n", encoding="utf-8")
    (after / "AGENT.md").write_text("Stop when done.\n", encoding="utf-8")

    stats = core.diff_stats(before, after, ignored_paths={"AGENT.md"})

    assert stats.changed_files == ["module.py"]
    assert stats.line_delta == 2
