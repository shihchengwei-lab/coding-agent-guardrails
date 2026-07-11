import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("corridor_v14", ROOT / "bin" / "corridor_ci.py")
corridor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = corridor
SPEC.loader.exec_module(corridor)


def artifact(fingerprint="a" * 64, risk="none-detected", approval=None):
    return {
        "schema": 1,
        "generator": {"agentcam_version": "0.6.0", "runtime_revision": "rev"},
        "delivery": {
            "base_commit": None,
            "product_fingerprint": fingerprint,
            "changed_files": [{"path": "src/app.py", "status": "modified"}],
            "outcomes": ["works"],
            "scope": ["src/app.py"],
            "scope_changes": [],
            "review_first": "src/app.py",
            "risk": risk,
        },
        "verification": {
            "level": "structural-only",
            "checks": [{
                "id": "structural",
                "argv": ["git", "diff", "--check"],
                "exit_code": 0,
                "duration_ms": 1,
                "state_fingerprint": fingerprint,
            }],
        },
        "capture": {"terminal": "unavailable", "coverage": "partial"},
        "approval": approval,
    }


class ReviewArtifactTest(unittest.TestCase):
    def evaluate(self, review, changed=None, deleted=None, fingerprint="a" * 64):
        return corridor.evaluate_review_artifact(
            changed_files=changed or ["src/app.py"],
            deleted_files=deleted,
            review=review,
            current_product_fingerprint=fingerprint,
            pr_title="PR",
            pr_url="url",
        )

    def test_artifact_replaces_pr_body_handoff_and_warns_structural_only(self):
        report = self.evaluate(
            artifact(), changed=["src/app.py", ".guardrails/review.json"]
        )
        self.assertTrue(report.ok)
        self.assertEqual(report.handoff["Decision"], "PR (url)")
        self.assertIn("structural-only", "\n".join(report.warnings))
        self.assertIn(".guardrails/review.json", report.changed_files)

    def test_missing_stale_and_underreported_artifacts_fail(self):
        missing = self.evaluate(None)
        stale = self.evaluate(artifact("b" * 64))
        underreported = self.evaluate(artifact(), changed=["src/auth/login.py"])
        self.assertFalse(missing.ok)
        self.assertFalse(stale.ok)
        self.assertFalse(underreported.ok)

    def test_high_risk_confirmation_must_match_product(self):
        bad = artifact(risk="high", approval={
            "required": True,
            "confirmed": True,
            "product_fingerprint": "b" * 64,
            "confirmation_id": "c" * 64,
        })
        report = self.evaluate(bad, changed=["src/auth/login.py"])
        self.assertFalse(report.ok)
        self.assertIn("confirmation", "\n".join(report.issues).lower())

    def test_tracked_deletion_sets_independent_high_risk_floor(self):
        review = artifact()
        report = self.evaluate(review, deleted=["src/app.py"])
        self.assertFalse(report.ok)
        issues = "\n".join(report.issues).lower()
        self.assertIn("risk", issues)
        self.assertIn("deleted", issues)

    def test_artifact_changed_files_must_match_current_product_paths(self):
        review = artifact()
        review["delivery"]["changed_files"] = [
            {"path": "other.py", "status": "modified"}
        ]
        report = self.evaluate(review)
        self.assertFalse(report.ok)
        self.assertIn("changed_files", "\n".join(report.issues))

    def test_partial_capture_warns_and_recorded_requires_primary(self):
        review = artifact()
        review["verification"]["level"] = "recorded"
        report = self.evaluate(review)
        self.assertFalse(report.ok)
        self.assertIn("primary", "\n".join(report.issues))
        warnings = "\n".join(report.warnings)
        self.assertIn("partial", warnings)
        self.assertIn("terminal", warnings)

    def test_required_schema_objects_and_check_duration_are_validated(self):
        review = artifact()
        review.pop("generator")
        review["delivery"].pop("outcomes")
        review["verification"]["checks"][0].pop("duration_ms")
        review["capture"] = {"terminal": "invented", "coverage": "complete-ish"}
        report = self.evaluate(review)
        self.assertFalse(report.ok)
        issues = "\n".join(report.issues)
        self.assertIn("generator", issues)
        self.assertIn("outcomes", issues)
        self.assertIn("duration_ms", issues)
        self.assertIn("capture", issues)


if __name__ == "__main__":
    unittest.main()
