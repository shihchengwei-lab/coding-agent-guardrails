# kiss-my-diff

![kiss-my-diff hero](assets/kiss-my-diff-hero.png)

Agents usually finish the task. The question is whether you want to kiss the diff afterward.

Benchmark result: 38% smaller patches, 19% fewer files touched.

`kiss-my-diff` is a tiny [`AGENT.md`](AGENT.md) for coding agents. It asks the agent to read first, use existing code, make the smallest readable change, avoid hiding invalid states, verify, and stop.

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

## Evidence

First, the benchmark had to pass a sanity check. Model strength is checked with correctness only, because clean-diff score measures coding discipline, not raw capability:

| baseline only | correctness |
| --- | ---: |
| `gpt-5.5` | 100.00 |
| `gpt-5.4` | 100.00 |
| `gpt-5.4-mini` | 100.00 |
| `gpt-5.3-codex-spark` | 100.00 |

Then the same 8 bugfix tasks were rerun with and without `kiss-my-diff`.

| what changed | baseline | kiss-my-diff | result |
| --- | ---: | ---: | ---: |
| correctness | 100.00 | 100.00 | no change |
| clean-diff score | 78.23 | 87.87 | +12.32% |
| overall score | 93.47 | 96.36 | +3.09% |
| files touched | 1.97 | 1.59 | 19.05% fewer |
| patch size | 43.25 lines | 27.00 lines | 37.57% smaller |

Scoring: correctness is public tests (35%) plus hidden tests (65%). Clean-diff is the average of file count, patch size, dependency changes, and task-specific quality checks. Overall score is 70% correctness and 30% clean-diff.

The useful part is the diff shape: agents touched fewer files and produced much smaller patches.

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

| model | correctness | clean-diff change | patch size |
| --- | ---: | ---: | ---: |
| `gpt-5.5` | 100.00 -> 100.00 | +10.12% | 30.63 -> 25.38 lines |
| `gpt-5.4` | 100.00 -> 100.00 | +12.21% | 37.13 -> 27.50 lines |
| `gpt-5.4-mini` | 100.00 -> 100.00 | +16.29% | 70.38 -> 30.63 lines |
| `gpt-5.3-codex-spark` | 100.00 -> 100.00 | +11.04% | 34.88 -> 24.50 lines |

This is still a small single-run benchmark, not a model leaderboard. The narrow claim is simpler: with the same tasks and models, `kiss-my-diff` made the patches smaller and more local.

## Use

Copy [`AGENT.md`](AGENT.md) into the root of a repo where coding agents work.

## License

MIT. See [`LICENSE`](LICENSE).
