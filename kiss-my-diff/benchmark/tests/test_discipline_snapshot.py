import hashlib
import re
from pathlib import Path


def test_fusion_result_is_bound_to_an_immutable_measured_fixture():
    lab = Path(__file__).resolve().parents[1]
    fixture = lab / "fixtures" / "discipline-fusion-20260705.md"
    run_doc = (lab / "discipline-fusion-run.md").read_text(encoding="utf-8")
    summary_doc = (lab / "discipline-fusion-summary.md").read_text(encoding="utf-8")

    digest = "sha256:" + hashlib.sha256(fixture.read_bytes()).hexdigest()
    assert digest in run_doc
    assert digest in summary_doc
    assert "historical measured fixture" in run_doc.lower()
    assert "historical measured fixture" in summary_doc.lower()

    documented = re.findall(r"sha256:[0-9a-f]{64}", run_doc + summary_doc)
    assert documented and set(documented) == {digest}
