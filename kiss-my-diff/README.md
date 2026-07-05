# kiss-my-diff

![kiss-my-diff hero](assets/kiss-my-diff-hero.png)

> In this monorepo the rules ship through the root installer as part of
> [`templates/DISCIPLINE.md`](../templates/DISCIPLINE.md). The numbers
> below were measured on [`AGENT.md`](AGENT.md) used standalone; the file
> is kept here verbatim as the measured specimen. The fused installer
> block has its own same-day two-arm run — 24.8% smaller patches, 9.8%
> fewer files touched, correctness unchanged on `gpt-5.5` — recorded in
> [`benchmark/discipline-fusion-run.md`](benchmark/discipline-fusion-run.md).

Agents usually finish the task. The question is whether you want to kiss the diff afterward.

Keep It Simple, Stupid for coding-agent diffs: smaller patches, fewer touched files.

Benchmark result: 31% smaller patches, 20% fewer files touched.

`kiss-my-diff` is a tiny [`AGENT.md`](AGENT.md) for coding agents. It turns KISS into a small rule file: read first, use existing code, make the smallest readable change, avoid hiding invalid states, verify, and stop.

## The File

```text
Build only what is needed now.
Prefer the smallest readable change.
Read the existing code before editing.
Use existing helpers and patterns before adding new code.
Use built-ins before adding dependencies.
Touch the fewest files needed.
Do not add abstractions for one-shot code.
Preserve existing behavior unless asked to change it.
Do not hide errors or invalid states.
Verify with the smallest relevant test.
Stop when done.
```

## Why

Modern coding agents can usually make tests pass. The common failure mode is overbuilding: extra files, new abstractions, duplicated helper logic, broader rewrites, or dependencies that were not needed.

This file is the small reminder: make the diff small enough to love.

## Benchmark Snapshot

This is a small benchmark, not proof or a model leaderboard. It asks a narrower question: on tasks the models could already solve, does the rule file make the solution smaller and more local?

Two benchmark snapshots were combined for baseline vs `kiss-my-diff`: 8 bugfix tasks across 4 models, run twice. That gives 64 baseline runs and 64 `kiss-my-diff` runs.

| variant | runs | correctness | files touched | patch size |
| --- | ---: | ---: | ---: | ---: |
| baseline | 64 | 100.00 | 1.97 | 39.34 lines |
| `kiss-my-diff` | 64 | 96.88 | 1.58, 19.84% fewer | 27.23 lines, 30.78% smaller |

Correctness is public tests (35%) plus hidden tests (65%).

In this larger pool, stronger models kept correctness at 100% with `kiss-my-diff`. This is a diff-discipline harness, not a correctness guarantee.

The benchmark harness and tasks are open source in [`benchmark/`](benchmark/). Hidden tests are checked in for reproducibility, but the runner keeps them out of the agent workspace during a run.

Calibration check: pass, but saturated. On the combined baseline runs, all four models scored 100.00 baseline capability, so no weaker model scored higher on correctness. This sanity check does not prove the task pool separates model strength; it only rules out the earlier inverted-baseline failure mode.

### Context Weighting

At the model level, a coding agent is still generating the next token from its context. `AGENT.md` is soft pressure, not a hard boundary: it changes the next-token distribution, but it does not mechanically enforce a rule. I tested heavier variants to look for the sweet spot between smaller patches and missed requirements. Details: [`benchmark/context-weighting-experiment.md`](benchmark/context-weighting-experiment.md).

### Per Model

Use this table to judge whether your model is likely to benefit from this repo. Lower files touched and patch size mean the change stayed smaller and more local.

| model | variant | correctness | files touched | patch size |
| --- | --- | ---: | ---: | ---: |
| `gpt-5.5` | baseline | 100.00 | 1.88 | 34.19 lines |
| `gpt-5.5` | `kiss-my-diff` | 100.00 | 1.44 | 23.31 lines |
| `gpt-5.4` | baseline | 100.00 | 1.94 | 36.69 lines |
| `gpt-5.4` | `kiss-my-diff` | 100.00 | 1.69 | 29.38 lines |
| `gpt-5.4-mini` | baseline | 100.00 | 2.31 | 54.56 lines |
| `gpt-5.4-mini` | `kiss-my-diff` | 100.00 | 1.69 | 31.50 lines |
| `gpt-5.3-codex-spark` | baseline | 100.00 | 1.75 | 31.94 lines |
| `gpt-5.3-codex-spark` | `kiss-my-diff` | 87.50 | 1.50 | 24.75 lines |

### Example Diff

One benchmark task asked the agent to stop hiding bad API responses. Both runs passed public and hidden tests.

Without `kiss-my-diff`: 2 files touched, 32 diff lines.

```diff
diff --git a/api/response.py b/api/response.py
 import json
+
+from api.errors import ResponseDecodeError
+
+REQUIRED_FIELDS = ("id", "status", "items")
 
 def parse_response(raw):
     try:
         payload = json.loads(raw)
-    except ValueError:
-        return {"id": None, "status": "unknown", "items": []}
+    except ValueError as exc:
+        raise ResponseDecodeError("Response is not valid JSON") from exc
+
+    if not isinstance(payload, dict):
+        raise ResponseDecodeError("Response payload must be an object")
+
+    missing_fields = [field for field in REQUIRED_FIELDS if field not in payload]
+    if missing_fields:
+        raise ResponseDecodeError(
+            f"Response payload is missing required fields: {', '.join(missing_fields)}"
+        )
+
+    if not isinstance(payload["items"], list):
+        raise ResponseDecodeError("Response payload field 'items' must be a list")
 
     return {
-        "id": payload.get("id"),
-        "status": payload.get("status", "unknown"),
-        "items": payload.get("items", []),
+        "id": payload["id"],
+        "status": payload["status"],
+        "items": payload["items"],
     }

diff --git a/tests/test_response.py b/tests/test_response.py
+def test_top_level_payload_must_be_an_object():
+    with pytest.raises(ResponseDecodeError):
+        parse_response('["not", "an", "object"]')
```

With `kiss-my-diff`: 1 file touched, 22 diff lines.

```diff
diff --git a/api/response.py b/api/response.py
 import json
+
+from api.errors import ResponseDecodeError
 
 def parse_response(raw):
     try:
         payload = json.loads(raw)
-    except ValueError:
-        return {"id": None, "status": "unknown", "items": []}
+    except ValueError as exc:
+        raise ResponseDecodeError("Response body is not valid JSON.") from exc
+
+    if not isinstance(payload, dict):
+        raise ResponseDecodeError("Response payload must be a JSON object.")
+
+    for field in ("id", "status", "items"):
+        if field not in payload:
+            raise ResponseDecodeError(f"Response payload is missing required field: {field}.")
+
+    if not isinstance(payload["items"], list):
+        raise ResponseDecodeError("Response field 'items' must be a list.")
 
     return {
-        "id": payload.get("id"),
-        "status": payload.get("status", "unknown"),
-        "items": payload.get("items", []),
+        "id": payload["id"],
+        "status": payload["status"],
+        "items": payload["items"],
     }
```

The narrow claim is simple: with the same tasks and models, `kiss-my-diff` made the patches smaller and more local.

## Use

Copy [`AGENT.md`](AGENT.md) into the root of a repo where coding agents work.

## License

MIT. See the repo root [`LICENSE`](../LICENSE).
