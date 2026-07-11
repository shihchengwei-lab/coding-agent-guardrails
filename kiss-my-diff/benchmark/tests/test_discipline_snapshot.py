import hashlib
from collections import Counter
from pathlib import Path

from benchmark_runner import find_results, write_summary


def test_fusion_measurement_is_committed_and_recomputable(tmp_path: Path):
    lab = Path(__file__).resolve().parents[1]
    fixture = lab / "fixtures" / "discipline-fusion-20260705.md"
    results_dir = lab / "results" / "discipline-fusion-20260705"
    result_file = results_dir / "result.json"
    committed_summary = results_dir / "summary.md"
    run_doc = (lab / "discipline-fusion-run.md").read_text(encoding="utf-8")

    fixture_digest = "sha256:" + hashlib.sha256(fixture.read_bytes()).hexdigest()
    results_digest = "sha256:" + hashlib.sha256(result_file.read_bytes()).hexdigest()
    assert fixture_digest in run_doc
    assert results_digest in run_doc

    rows = find_results(results_dir)
    assert len(rows) == 32
    assert Counter(row["variant"] for row in rows) == {
        "baseline": 16,
        "discipline": 16,
    }

    recomputed = tmp_path / "summary.md"
    write_summary(rows, recomputed)
    assert recomputed.read_text(encoding="utf-8").splitlines() == (
        committed_summary.read_text(encoding="utf-8").splitlines()
    )
