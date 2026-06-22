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

## Benchmark Snapshot

This is a small single-run benchmark, not proof or a model leaderboard. It asks a narrower question: on tasks the models could already solve, does the rule file make the solution smaller and more local?

8 bugfix tasks were run across 4 models, with and without `kiss-my-diff`.

| metric | result |
| --- | ---: |
| correctness | 100.00 -> 100.00 |
| clean-diff score | +12.32% |
| files touched | 19.05% fewer |
| patch size | 37.57% smaller |

Clean-diff is the average of file count, patch size, dependency changes, and task-specific quality checks. Correctness is public tests (35%) plus hidden tests (65%).

### Per Model

Use this table to judge whether your model is likely to benefit from this repo: higher clean-diff gain means the same model tended to produce smaller, more local patches when the file was present.

| model | correctness | clean-diff change | patch size |
| --- | ---: | ---: | ---: |
| `gpt-5.5` | 100.00 -> 100.00 | +10.12% | 30.63 -> 25.38 lines |
| `gpt-5.4` | 100.00 -> 100.00 | +12.21% | 37.13 -> 27.50 lines |
| `gpt-5.4-mini` | 100.00 -> 100.00 | +16.29% | 70.38 -> 30.63 lines |
| `gpt-5.3-codex-spark` | 100.00 -> 100.00 | +11.04% | 34.88 -> 24.50 lines |

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

MIT. See [`LICENSE`](LICENSE).
