# kiss-my-diff

[English](README.md)

![kiss-my-diff hero](assets/kiss-my-diff-hero.png)

AI coding agent 通常能把任務做完。麻煩的是，它也常順手多改幾個檔案、多包一層抽象，或加一個其實不需要的依賴。

`kiss-my-diff` 想做的事很小：讓最後那個 diff 乾淨到你願意看完。

Benchmark 結果：patch 小 38%，觸碰檔案少 19%。

`kiss-my-diff` 是一份很小的 [`AGENT.md`](AGENT.md)，給 coding agent 用。它提醒 agent 先讀現有程式、沿用既有模式、做最小且可讀的修改、不要把錯誤或非法狀態藏起來、驗證結果，然後停下來。

## 這份檔案

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

## 為什麼需要

會過測，不代表 diff 好維護。常見的問題不是 AI 寫不出來，而是它做太多：多改檔案、重複既有 helper、擴大重寫範圍、加不必要的抽象，或把一個小 bugfix 做成一個小框架。

這份檔案不是要 agent 變保守，而是把它拉回當前任務：先理解現有程式，做剛好需要的修改，驗證，然後收手。

## Benchmark 摘要

這是一組小型、單次執行的 benchmark，不是嚴格證明，也不是模型排行榜。它只看一件事：在模型本來就能修好的任務上，這份規則檔會不會讓解法更小、更集中。

8 個 bugfix 任務，跨 4 個模型，各自跑有無 `kiss-my-diff` 的版本。

| 指標 | 結果 |
| --- | ---: |
| 正確率 | 100.00 -> 100.00 |
| clean-diff 分數 | +12.32% |
| 觸碰檔案數 | 少 19.05% |
| patch 大小 | 小 37.57% |

Clean-diff 是檔案數、patch 大小、依賴變更、任務特定品質檢查的平均。正確率是公開測試 35% 加隱藏測試 65%。

### 各模型結果

這張表不是在排模型強弱，而是讓你看同一個模型加上 `kiss-my-diff` 之後的變化。如果你用的模型 clean-diff gain 越高，代表它越容易被這份規則拉回小 patch。

| 模型 | 正確率 | clean-diff 變化 | patch 大小 |
| --- | ---: | ---: | ---: |
| `gpt-5.5` | 100.00 -> 100.00 | +10.12% | 30.63 -> 25.38 lines |
| `gpt-5.4` | 100.00 -> 100.00 | +12.21% | 37.13 -> 27.50 lines |
| `gpt-5.4-mini` | 100.00 -> 100.00 | +16.29% | 70.38 -> 30.63 lines |
| `gpt-5.3-codex-spark` | 100.00 -> 100.00 | +11.04% | 34.88 -> 24.50 lines |

### Before / After Diff

其中一題是 API response decoding。原本的程式會用預設值吞掉壞掉的 upstream response；任務要求改成明確丟出 `ResponseDecodeError`。兩次都通過公開測試和隱藏測試，但 diff 長相不同。

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

重點不在誰比較聰明，而是在同樣能修好的情況下，`kiss-my-diff` 比較常把修改留在該改的地方。

## 使用方式

把 [`AGENT.md`](AGENT.md) 放到 coding agent 會工作的 repo 根目錄。

## 授權

MIT。見 [`LICENSE`](LICENSE)。
