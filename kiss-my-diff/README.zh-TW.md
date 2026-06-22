# kiss-my-diff

[English](README.md)

![kiss-my-diff hero](assets/kiss-my-diff-hero.png)

Agent 通常能把任務做完。問題是：做完之後，你還想不想親一下那個 diff。

Benchmark 結果：patch 少 38%，觸碰檔案少 19%。

`kiss-my-diff` 是一份很小的 [`AGENT.md`](AGENT.md)，給 coding agent 用。它提醒 agent 先讀現有程式、優先使用既有程式碼、做最小且可讀的修改、不要把非法狀態藏起來、驗證結果，然後停下來。

## 檔案內容

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

## 為什麼

現代 coding agent 通常能讓測試通過。常見問題不是做不出來，而是做太多：多改檔案、加不必要的抽象、重複既有 helper、擴大重寫範圍，或加入其實不需要的依賴。

這份檔案就是一個小提醒：把 diff 做到小到值得喜歡。

## Benchmark Snapshot

這是一組小型、單次執行的 benchmark，不是證明，也不是模型排行榜。它問的是比較窄的問題：在模型本來就能解的任務上，這份規則檔會不會讓解法更小、更集中？

8 個 bugfix 任務，跨 4 個模型，各自跑有無 `kiss-my-diff` 的版本。

| 指標 | 結果 |
| --- | ---: |
| correctness | 100.00 -> 100.00 |
| clean-diff score | +12.32% |
| 觸碰檔案 | 少 19.05% |
| patch size | 小 37.57% |

Clean-diff 是檔案數、patch 大小、依賴變更、任務特定品質檢查的平均。Correctness 是公開測試 35% 加隱藏測試 65%。

### 各模型結果

可以用這張表判斷你使用的模型是否可能受益：clean-diff gain 越高，代表同一個模型在有這份檔案時，傾向產生更小、更集中的 patch。

| 模型 | correctness | clean-diff 變化 | patch size |
| --- | ---: | ---: | ---: |
| `gpt-5.5` | 100.00 -> 100.00 | +10.12% | 30.63 -> 25.38 lines |
| `gpt-5.4` | 100.00 -> 100.00 | +12.21% | 37.13 -> 27.50 lines |
| `gpt-5.4-mini` | 100.00 -> 100.00 | +16.29% | 70.38 -> 30.63 lines |
| `gpt-5.3-codex-spark` | 100.00 -> 100.00 | +11.04% | 34.88 -> 24.50 lines |

### Before / After Diff

其中一個 benchmark 任務要求 agent 不要再隱藏壞掉的 API response。兩次執行都通過公開測試和隱藏測試。

沒有 `kiss-my-diff`：觸碰 2 個檔案，32 行 diff。

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

有 `kiss-my-diff`：觸碰 1 個檔案，22 行 diff。

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

主張很窄：在同一組任務和模型上，`kiss-my-diff` 讓 patch 更小、更集中。

## 使用方式

把 [`AGENT.md`](AGENT.md) 複製到 coding agent 會工作的 repo 根目錄。

## 授權

MIT。見 [`LICENSE`](LICENSE)。
