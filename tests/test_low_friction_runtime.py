import importlib.machinery
import importlib.util
import json
import subprocess
import sys
from types import SimpleNamespace
from io import StringIO
from contextlib import redirect_stdout
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATCH_COST = ROOT / "slime-coding" / "bin" / "patch-cost"
loader = importlib.machinery.SourceFileLoader("low_friction_runtime", str(PATCH_COST))
spec = importlib.util.spec_from_loader(loader.name, loader)
runtime = importlib.util.module_from_spec(spec)
loader.exec_module(runtime)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True,
    ).stdout.strip()


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test")
    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    return repo


def start(repo: Path, turn: str = "turn-1") -> dict:
    payload = {
        "hook_event_name": "UserPromptSubmit",
        "turn_id": turn,
        "session_id": "session-1",
        "cwd": str(repo),
        "prompt": "fix the product",
    }
    runtime.record_baseline(payload)
    return payload


def test_scope_is_git_local_and_direct_edit_has_agent_facing_remedy(tmp_path):
    repo = make_repo(tmp_path)
    payload = start(repo)

    output = StringIO()
    with redirect_stdout(output):
        runtime.scope_gate({
            **payload,
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": str(repo / "src" / "app.py")},
        })
    assert "guardrails internal scope set" in output.getvalue()
    assert ".slime" not in output.getvalue()

    runtime.set_delivery_scope(repo, "observable result", ["src/app.py"])
    scope_path = runtime.delivery_scope_path(repo)
    assert scope_path.is_file()
    assert str(scope_path).startswith(str(repo / ".git" / "guardrails"))
    assert not (repo / ".slime").exists()

    output = StringIO()
    with redirect_stdout(output):
        runtime.scope_gate({
            **payload,
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": str(repo / "src" / "app.py")},
        })
    assert output.getvalue() == ""


def test_repository_metadata_still_requires_declared_scope(tmp_path):
    repo = make_repo(tmp_path)
    payload = start(repo)
    output = StringIO()
    with redirect_stdout(output):
        runtime.scope_gate({
            **payload,
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": str(repo / "CHANGELOG.md")},
        })
    assert "permissionDecision\": \"deny" in output.getvalue()
    assert "guardrails internal scope set" in output.getvalue()


def test_stop_writes_single_structural_review_artifact(tmp_path):
    repo = make_repo(tmp_path)
    payload = start(repo)
    runtime.set_delivery_scope(repo, "observable result", ["src/app.py"])
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("changed = True\n", encoding="utf-8")

    result = runtime.finish_delivery(repo, payload)

    assert result["decision"] == "ready"
    artifact = json.loads((repo / ".guardrails" / "review.json").read_text("utf-8"))
    assert artifact["schema"] == 1
    assert artifact["delivery"]["scope"] == ["src/app.py"]
    assert artifact["delivery"]["changed_files"] == [
        {"path": "src/app.py", "status": "untracked"}
    ]
    assert artifact["verification"]["level"] == "structural-only"
    assert artifact["verification"]["checks"][0]["id"] == "structural"
    assert artifact["approval"] is None
    serialized = json.dumps(artifact)
    assert "fix the product" not in serialized
    assert "turn-1" not in serialized
    assert "session-1" not in serialized


def test_high_risk_requires_exact_prompt_and_edit_invalidates_approval(tmp_path):
    repo = make_repo(tmp_path)
    payload = start(repo)
    runtime.set_delivery_scope(repo, "secure login", ["src/auth/login.py"])
    (repo / "src" / "auth").mkdir(parents=True)
    target = repo / "src" / "auth" / "login.py"
    target.write_text("secure = True\n", encoding="utf-8")

    blocked = runtime.finish_delivery(repo, payload)
    assert blocked["decision"] == "block"
    phrase = blocked["confirmation_phrase"]
    assert phrase.startswith("確認高風險變更 ")
    assert not (repo / ".guardrails" / "review.json").exists()
    assert not runtime.accept_high_risk_prompt(repo, {**payload, "prompt": phrase + "x"})
    approval_payload = {**payload, "turn_id": "turn-2", "prompt": f"  {phrase}  "}
    assert runtime.accept_high_risk_prompt(repo, approval_payload)

    ready = runtime.finish_delivery(repo, approval_payload)
    assert ready["decision"] == "ready"
    artifact = json.loads((repo / ".guardrails" / "review.json").read_text("utf-8"))
    assert artifact["approval"]["confirmed"] is True
    assert artifact["approval"]["product_fingerprint"] == artifact["delivery"]["product_fingerprint"]

    target.write_text("secure = False\n", encoding="utf-8")
    stale = runtime.finish_delivery(repo, approval_payload)
    assert stale["decision"] == "block"
    assert stale["confirmation_phrase"] != phrase


def test_high_risk_confirmation_reuses_state_bound_checks(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    payload = start(repo)
    runtime.set_delivery_scope(repo, "secure login", ["src/auth/login.py"])
    (repo / "src" / "auth").mkdir(parents=True)
    (repo / "src" / "auth" / "login.py").write_text("secure = True\n", encoding="utf-8")
    original = runtime._run_review_checks
    calls = 0

    def counted(cwd, fingerprint):
        nonlocal calls
        calls += 1
        return original(cwd, fingerprint)

    monkeypatch.setattr(runtime, "_run_review_checks", counted)
    blocked = runtime.finish_delivery(repo, payload)
    assert calls == 1
    approved_payload = {
        **payload,
        "turn_id": "turn-approved",
        "prompt": blocked["confirmation_phrase"],
    }
    assert runtime.accept_high_risk_prompt(repo, approved_payload)
    assert runtime.finish_delivery(repo, approved_payload)["decision"] == "ready"
    assert calls == 1


def test_scope_expansion_records_reason(tmp_path):
    repo = make_repo(tmp_path)
    start(repo)
    runtime.set_delivery_scope(repo, "observable result", ["src/app.py"])
    runtime.add_delivery_scope(repo, ["src/shared.py"], "existing owner is here")

    state = runtime.read_delivery_scope(repo)
    assert state["paths"] == ["src/app.py", "src/shared.py"]
    assert state["changes"] == [{
        "added": ["src/shared.py"],
        "reason": "existing owner is here",
    }]


def test_review_artifact_aggregates_committed_changes_across_turns(tmp_path):
    repo = make_repo(tmp_path)
    git(repo, "switch", "-qc", "feature")
    first = start(repo, "turn-a")
    runtime.set_delivery_scope(repo, "delivery", ["src/app.py"])
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("first = True\n", encoding="utf-8")
    assert runtime.finish_delivery(repo, first)["decision"] == "ready"
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "first turn")

    second = start(repo, "turn-b")
    runtime.add_delivery_scope(repo, ["src/shared.py"], "second attachment point")
    (repo / "src" / "shared.py").write_text("second = True\n", encoding="utf-8")
    assert runtime.finish_delivery(repo, second)["decision"] == "ready"

    review = json.loads((repo / ".guardrails" / "review.json").read_text("utf-8"))
    assert [item["path"] for item in review["delivery"]["changed_files"]] == [
        "src/app.py", "src/shared.py",
    ]


def test_agentcam_canonical_high_path_requires_confirmation_before_finalize(tmp_path):
    repo = make_repo(tmp_path)
    payload = start(repo)
    runtime.set_delivery_scope(repo, "update local environment", [".env"])
    (repo / ".env").write_text("MODE=test\n", encoding="utf-8")

    result = runtime.finish_delivery(repo, payload)

    assert result["decision"] == "block"
    assert result["confirmation_phrase"].startswith("確認高風險變更 ")
    assert "secret-like filename" in result["reason"]
    assert not (repo / ".guardrails" / "review.json").exists()


def test_review_artifact_atomic_failure_keeps_delivery_retryable(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    payload = start(repo)
    runtime.set_delivery_scope(repo, "observable result", ["src/app.py"])
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("changed = True\n", encoding="utf-8")
    original = runtime._atomic_json
    failed = False

    def fail_review_once(path, value):
        nonlocal failed
        if str(path).endswith(".guardrails/review.json") and not failed:
            failed = True
            raise OSError("injected artifact failure")
        return original(path, value)

    monkeypatch.setattr(runtime, "_atomic_json", fail_review_once)
    blocked = runtime.finish_delivery(repo, payload)
    assert blocked["decision"] == "block"
    assert "artifact" in blocked["reason"].lower()
    assert runtime.load_baseline(repo, payload) is not None
    assert not (repo / ".guardrails" / "review.json").exists()

    retried = runtime.finish_delivery(repo, payload)
    assert retried["decision"] == "ready"
    assert (repo / ".guardrails" / "review.json").is_file()


def test_pr_sync_posts_exact_head_approval_once(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    head = git(repo, "rev-parse", "HEAD")
    artifact = {
        "approval": {"confirmed": True, "product_fingerprint": "fp"},
        "delivery": {
            "product_fingerprint": "fp",
            "changed_files": [{"path": "requirements.txt", "status": "modified"}],
        },
    }
    (repo / ".guardrails").mkdir()
    (repo / ".guardrails" / "review.json").write_text(json.dumps(artifact), encoding="utf-8")
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        if argv[:3] == ["gh", "pr", "view"]:
            return SimpleNamespace(returncode=0, stdout=json.dumps({
                "number": 12, "headRefOid": head, "comments": [],
            }), stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(runtime.subprocess, "run", fake_run)
    monkeypatch.setattr(runtime, "current_head", lambda cwd: head)
    first = runtime.sync_pr_approval(repo)
    assert first["comments"] == [f"Guardrails-Dependency-Approval: {head}"]
    assert [call for call in calls if call[:3] == ["gh", "pr", "comment"]]

    calls.clear()
    def fake_existing(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            "number": 12,
            "headRefOid": head,
            "comments": [{"body": f"Guardrails-Dependency-Approval: {head}"}],
        }), stderr="")
    monkeypatch.setattr(runtime.subprocess, "run", fake_existing)
    second = runtime.sync_pr_approval(repo)
    assert second["comments"] == []
    assert not [call for call in calls if call[:3] == ["gh", "pr", "comment"]]


def test_pr_sync_refuses_head_mismatch(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    artifact = {
        "approval": {"confirmed": True, "product_fingerprint": "fp"},
        "delivery": {
            "product_fingerprint": "fp",
            "changed_files": [{"path": ".github/workflows/ci.yml", "status": "modified"}],
        },
    }
    (repo / ".guardrails").mkdir()
    (repo / ".guardrails" / "review.json").write_text(json.dumps(artifact), encoding="utf-8")
    monkeypatch.setattr(runtime.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(
        returncode=0,
        stdout=json.dumps({"number": 12, "headRefOid": "0" * 40, "comments": []}),
        stderr="",
    ))
    monkeypatch.setattr(runtime, "current_head", lambda cwd: "f" * 40)

    try:
        runtime.sync_pr_approval(repo)
    except ValueError as exc:
        assert "head SHA" in str(exc)
    else:
        raise AssertionError("head mismatch must be rejected")


def test_review_check_argv_is_redacted_before_artifact_storage(tmp_path):
    repo = make_repo(tmp_path)
    git_dir = Path(git(repo, "rev-parse", "--absolute-git-dir"))
    config = git_dir / "guardrails" / "config.json"
    config.parent.mkdir(parents=True)
    secret = "sk-AAAAAAAAAAAAAAAAAAAA"
    config.write_text(json.dumps({
        "schema": 1,
        "checks": {
            "primary": {
                "argv": [sys.executable, "-c", "pass", f"API_TOKEN={secret}"],
                "timeout_seconds": 30,
            }
        },
    }), encoding="utf-8")

    checks, error = runtime._run_review_checks(repo, "f" * 64)

    assert error is None
    assert secret not in json.dumps(checks)
    assert "REDACTED" in json.dumps(checks)
