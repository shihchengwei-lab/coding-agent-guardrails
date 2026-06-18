# Slime Coding：黏菌式雙向收斂的最小修改方法

版本：v0.2  
日期：2026-06-18  
狀態：概念文件  
用途：定義 Slime Coding 的核心概念、操作流程與適用邊界。部署到 Claude Code、hooks、skill、commands 的細節放在 README 與 `install.sh`，不放在本文件。

---

## 0. 一句話

Slime Coding 是一種約束 Agentic AI 過度實作的 coding 方法：

> 不讓 AI 從 prompt 直接長出完整程式；先讓「目標行為」與「現有 repo」各自長出前沿，找到兩邊交會的最小走廊後，只沿那條走廊做最小修改。

它借用兩個直覺：

- **黏菌**：有流量與營養回饋的管路變粗，沒有流量的管路萎縮。
- **雙向導航**：起點與終點同時展開搜尋，兩邊接上後形成候選路徑。

轉成 coding 語言：

```text
需求不是直接變成 code。
需求先變成可觀察的 Goal Frontier。
repo 先變成可接上的 Start Frontier。
兩者接上的地方才是 Meeting Corridor。
只有 Meeting Corridor 可以進入實作。
```

---

## 1. 材料：Slime Coding 要解決什麼

Agentic AI 常見失敗不是「完全不會寫 code」，而是「寫太多 code」。

常見路徑如下：

```text
使用者下 prompt
→ AI 自行補完需求
→ AI 自行設計完整架構
→ AI 新增 helper / abstraction / fallback / config / dependency
→ patch 變大
→ 表面完成，但維護成本上升
```

這個失敗來自三個缺口：

1. **起點缺口**：AI 沒先確認 repo 目前已經有哪些可接結構。
2. **終點缺口**：AI 沒把需求反推成可觀察的驗收條件。
3. **停止缺口**：AI 沒有明確規則判斷「已經夠了，該停止」。

Slime Coding 的核心目標是補第三個缺口，同時用起點與終點前沿降低前兩個缺口。

---

## 2. 結論：Slime Coding 的核心規則

Slime Coding 的最小規則是：

```text
No code before corridor.
```

也就是：

```text
沒有 Goal Frontier，不准實作。
沒有 Start Frontier，不准實作。
沒有 Meeting Corridor，不准實作。
沒有 Stop Condition，不准實作。
```

完整規則如下：

1. **先定義終點，不先寫 code。** 需求必須先轉成可觀察行為與驗收條件。
2. **先確認起點，不重造 repo 已有的東西。** 現有入口、資料流、元件、測試、pattern 必須先被列出。
3. **只找交會走廊，不設計完整世界。** 實作範圍只限於起點與終點接上的最小路徑。
4. **有 evidence 的路徑加粗。** 通過 grep、測試、型別檢查、實際檔案閱讀、runtime log 的路徑才提高優先權。
5. **沒有 evidence 的路徑萎縮。** 猜測型、重構型、架構型分支若無必要證據，就剪掉。
6. **剪掉的路要記錄。** 被否決的設計不能在下一輪 agentic loop 裡無聲復活。
7. **達到停止條件就停。** 不因為 AI 還能美化、抽象、補 fallback，就繼續修改。

---

## 3. 核心名詞

### 3.1 Food Point：食物點

食物點是目標側的可觀察完成條件。

它不是抽象願望，而是能被使用者、測試、log、畫面或輸出驗收的結果。

範例：

```text
需求：新增 CSV 匯出功能。

食物點：
- 使用者點 Export 後下載 .csv。
- CSV 欄位順序固定為 name,email,created_at。
- 目前畫面上的 filter 必須影響匯出資料。
- 空資料時仍輸出 header。
- 不新增後端 endpoint，除非現有前端拿不到資料。
```

食物點越清楚，AI 越不需要自行補需求。

---

### 3.2 Goal Frontier：終點前沿

Goal Frontier 是從食物點反推回來的必要行為集合。

它回答：

```text
要完成目標，最少需要哪些行為？
哪些行為可以觀察？
哪些行為可以測試？
哪些東西明確不需要？
```

範例：

```text
Goal Frontier：
- 需要一個 UI 入口：Export button。
- 需要取得目前畫面上的 filtered rows。
- 需要把 rows serialize 成 CSV。
- 需要觸發 browser download。
- 需要測試空資料與 filter 後資料。
- 不需要新增後端 endpoint，除非前端沒有資料來源。
```

---

### 3.3 Start Frontier：起點前沿

Start Frontier 是目前 repo 已存在、可以接上目標的結構。

它回答：

```text
現在已經有什麼？
哪裡可以接？
哪裡不需要重做？
哪些現有 pattern 應該沿用？
```

範例：

```text
Start Frontier：
- DataTable.tsx 已經持有 filteredRows。
- Toolbar 已有 Button component。
- utils/exportJson.ts 已有下載檔案邏輯。
- 現有測試使用 @testing-library/react。
```

---

### 3.4 Meeting Corridor：交會走廊

Meeting Corridor 是 Goal Frontier 與 Start Frontier 接上的最小修改路徑。

它不是完整設計。  
它是「現有 repo 最少改哪裡，才能接上目標行為」。

範例：

```text
終點要求：CSV 必須反映目前 filter。
起點發現：DataTable.tsx 已經持有 filteredRows。
交會點：在 DataTable toolbar 加 Export button，直接使用 filteredRows 產生 CSV。

Meeting Corridor：
- 修改 DataTable.tsx：加入 Export button。
- 新增或擴充 csv serializer：只處理目前 rows → CSV string。
- 增加 DataTable 匯出測試：filter 後資料、空資料 header。
```

---

### 3.5 Slime Flow：黏液流量

Slime Flow 是某條候選路徑獲得的 evidence 強度。

會增加流量的 evidence：

```text
- 真的讀到相關檔案。
- grep 找到現有入口。
- stack trace 指到同一區域。
- 測試覆蓋到該區域。
- 型別檢查支持該接法。
- runtime log 支持該資料流。
- 多個獨立線索指向同一檔案或 function。
```

會降低流量的訊號：

```text
- 需要新增大型依賴。
- 需要重寫無關資料流。
- 需要更動 public API。
- 需要新增抽象層但只有一處使用。
- 沒有測試或 runtime evidence。
- 只是「看起來比較乾淨」的重構。
```

---

### 3.6 Pruned Path：剪枝路徑

Pruned Path 是被明確否決的候選路徑。

剪枝不是「忘記」。  
剪枝是把失敗路線寫成狀態，防止 agent 下一輪復活同一個錯誤設計。

範例：

```text
Pruned Path：
- 新增 /api/export-csv endpoint。
- 原因：前端已持有 filteredRows，不需要新增後端。
- evidence：DataTable.tsx 已讀到 filteredRows；現有前端資料足夠。
- 恢復條件：若後續發現 filteredRows 缺少 server-only 欄位，才重新考慮。
```

---

### 3.7 Stop Condition：停止條件

Stop Condition 是「什麼狀態下必須停止修改」。

範例：

```text
Stop Condition：
- Export button 出現。
- 點擊後下載 CSV。
- CSV 使用 filteredRows。
- 空資料輸出 header。
- 相關測試通過。
- 未新增後端 endpoint。
- 未新增 dependency。
```

Stop Condition 的目的不是追求完美，而是防止 AI 在達標後繼續加戲。

---

## 4. 運算直覺

Slime Coding 的流程可以寫成：

```text
Food Points
    ↓
Goal Frontier  ←───────┐
                       │
                 Meeting Corridor
                       │
Start Frontier ←────────┘
    ↑
Current Repo
```

再加上黏菌式回饋：

```text
候選路徑出現
→ evidence 增加，路徑變粗
→ evidence 不足，路徑萎縮
→ 成本過高，路徑剪掉
→ 只保留最小交會走廊
→ 沿走廊實作
→ 達到停止條件後停止
```

這不是讓 AI 更自由。  
這是讓 AI 的自由探索在進入實作前先收斂。

---

## 5. 最小語義位移

Slime Coding 不把「最短路徑」定義成最少行數。

coding 裡的最短路徑應該是 **最小語義位移**。

成本函數可以粗略寫成：

```text
Patch Cost =
  touched_files
+ new_files
+ new_dependencies
+ public_api_changes
+ new_abstractions
+ unrelated_refactors
+ untested_behavior
+ context_required_to_understand_patch
```

因此，一條好走廊通常長這樣：

```text
- 使用現有入口。
- 使用現有資料流。
- 使用現有 component / helper / pattern。
- 只補缺的那一小段。
- 測試直接對應食物點。
```

一條壞走廊通常長這樣：

```text
- 新增一套平行架構。
- 新增 dependency 只為了解一個小問題。
- 把單點需求抽象成 framework。
- 重構與目標無關的檔案。
- 用「順手整理」包裝無關修改。
```

---

## 6. 操作流程

### Phase 0：Discovery

當需求太模糊，先做 discovery，不進入 Slime Coding。

Discovery 的輸出不是 code，而是更清楚的食物點。

```text
模糊需求：讓報表更好用。

Discovery 應先問或查：
- 哪個報表？
- 誰用？
- 現在卡在哪？
- 完成後畫面或輸出有什麼可觀察變化？
- 有沒有不能改的部分？
```

需求能寫成可觀察條件後，再進入 Phase 1。

---

### Phase 1：Goal Frontier

把需求反推成可觀察條件、必要行為、限制條件、停止條件。

輸出格式：

```md
## Goal Frontier

### Food Points
- ...

### Required Behaviors
- ...

### Constraints
- ...

### Stop Condition
- ...
```

---

### Phase 2：Start Frontier

從 repo 正向找可接點。

這一階段只允許導航與查證，不允許實作。

輸出格式：

```md
## Start Frontier

### Existing Entry Points
- ...

### Existing Data Flow
- ...

### Existing Patterns
- ...

### Tests / Probes
- ...

### Unknowns
- ...
```

---

### Phase 3：Meeting Corridor

把 Goal Frontier 和 Start Frontier 對齊。

輸出格式：

```md
## Meeting Corridor

### Connection
- Goal requirement: ...
- Existing repo support: ...
- Minimal connection: ...

### Allowed Changes
- ...

### Forbidden Changes
- ...

### Pruned Paths
- Path: ...
  Reason: ...
  Evidence: ...
  Reopen condition: ...
```

---

### Phase 4：Minimal Patch

只沿 Meeting Corridor 實作。

實作規則：

```text
- 不新增依賴，除非 corridor 明確允許。
- 不新增抽象層，除非至少兩處已需要共用。
- 不重構 corridor 外檔案。
- 不修改 public API，除非 goal frontier 明確需要。
- 每個修改都要能回指到 food point 或 corridor item。
```

---

### Phase 5：Verification and Stop

驗證結果只回答三件事：

```text
- Food Points 是否滿足？
- Corridor 是否被遵守？
- Stop Condition 是否成立？
```

若 Stop Condition 成立，停止。

若失敗，補登 Pruned Path，再回到 Phase 2 或 Phase 3。  
不要從 prompt 重新生成完整方案。

---

## 7. 建議 artifact

Slime Coding 可以只靠文件手動執行，也可以進一步被工具強制。

概念層建議至少保留兩個 artifact：

```text
.slime/corridor.md
.slime/PRUNED.md
```

### 7.1 `.slime/corridor.md`

用途：保存本輪允許實作的最小走廊。

建議格式：

```md
# Corridor: <task name>

## Goal Frontier
- ...

## Start Frontier
- ...

## Meeting Corridor
- ...

## Allowed Files
- ...

## Forbidden Changes
- ...

## Stop Condition
- ...
```

### 7.2 `.slime/PRUNED.md`

用途：保存被剪掉的路徑，防止下一輪復活。

建議格式：

```md
# Pruned Paths

## <date> / <task>

### Path
- ...

### Reason
- ...

### Evidence
- ...

### Reopen Condition
- ...
```

---

## 8. Prompt 模板

### 8.1 Slime Navigate

```md
你現在不是 implementation agent。
你是 Slime Coding navigator。

任務：找出從目前 repo 到目標行為的最小修改走廊。

規則：
1. 先不要寫 code。
2. 先產出 Goal Frontier。
3. 再產出 Start Frontier。
4. 找出兩者交會的 Meeting Corridor。
5. 列出 Allowed Changes 與 Forbidden Changes。
6. 列出 Pruned Paths 與剪枝理由。
7. 定義 Stop Condition。
8. 在 corridor 完成前，不要進入實作。
```

### 8.2 Slime Implement

```md
只沿已確認的 Meeting Corridor 實作。

限制：
- 不新增依賴，除非 corridor 明確允許。
- 不新增抽象層，除非 corridor 明確允許。
- 不重構 corridor 外檔案。
- 不修改 public API，除非 corridor 明確允許。
- 每個修改都要能回指到 Goal Frontier 或 Meeting Corridor。

完成後只回報：
1. 修改摘要。
2. 對應的 Food Points。
3. 測試或檢查結果。
4. 是否達到 Stop Condition。
5. 未覆蓋風險。
```

### 8.3 Slime Review

```md
請審查這個 patch 是否符合 Slime Coding。

請檢查：
1. 每個 touched file 是否在 corridor 中。
2. 是否新增 corridor 外的功能。
3. 是否新增不必要 abstraction / dependency / fallback。
4. 是否有 pruned path 被復活。
5. Stop Condition 是否已經成立。
6. 如果已成立，指出哪些修改應停止或回退。
```

---

## 9. 適用場景

Slime Coding 適合：

```text
- 已有 repo，需要做小到中型功能修改。
- bugfix，需要從錯誤訊息接回現有 code。
- UI / API / workflow 有明確可觀察結果。
- 使用者想避免 AI 過度重構。
- 任務需要 agent 探索，但不希望 agent 自由實作。
```

Slime Coding 不適合：

```text
- 完全空白的新專案初始化。
- 需求仍停留在創意發想，沒有可觀察條件。
- 需要大規模重新架構，而且使用者已接受大 patch。
- research spike：目標是探索可行性，不是交付最小修改。
- 沒有任何測試、log、畫面、輸出可驗收的任務。
```

遇到不適合場景時，先做 discovery 或 architecture planning。  
不要把 Slime Coding 硬套成形式主義。

---

## 10. 與 Repo Map 的關係

Repo map 是地圖工具。  
Slime Coding 是導航紀律。

兩者關係如下：

```text
Repo map 幫 AI 知道 repo 裡有什麼。
Slime Coding 規定 AI 什麼時候可以動手、該動哪裡、何時停止。
```

Repo map 可以幫 Start Frontier 形成得更快。  
但只有 repo map 不會自動防止過度實作。

Slime Coding 關心的是：

```text
不是讓 AI 看更多。
而是讓 AI 在足夠 evidence 前不要寫；在達到 stop condition 後不要繼續寫。
```

---

## 11. 與部署（README / install.sh）的關係

本文件定義 Slime Coding 的概念層。

工程承載層（見 README 與 `install.sh`）處理的是，例如：

```text
- 哪些規則放在 CLAUDE.md。
- 哪些狀態寫入 PRUNED.md。
- 哪些條件用 hook hard-block。
- 哪些成本訊號只 report，不 block。
- 如何 clone 後用 install.sh 接進專案。
```

概念文件回答：

```text
Slime Coding 是什麼？
為什麼需要它？
如何手動運用它？
哪些 artifact 必須存在？
```

工程承載層回答：

```text
如何讓這些規則在 Claude Code 裡真的生效？
哪些地方靠請求？
哪些地方要強制？
哪些地方只能量測？
```

---

## 12. 最小實例

需求：在既有資料表加入 CSV 匯出。

### Goal Frontier

```text
Food Points：
- 使用者點 Export 後下載 CSV。
- CSV 使用目前 filter 後的資料。
- 空資料仍有 header。
- 不新增後端 endpoint。

Stop Condition：
- Export button 可用。
- 下載內容符合欄位順序。
- filter 後資料正確。
- 測試通過。
```

### Start Frontier

```text
- DataTable.tsx 已持有 filteredRows。
- Toolbar 已有 Button。
- exportJson.ts 已有下載檔案 helper。
- DataTable.test.tsx 已有互動測試。
```

### Meeting Corridor

```text
- 在 DataTable.tsx 的 toolbar 加 Export button。
- 新增 rowsToCsv 小函式。
- 重用既有下載 helper。
- 新增 DataTable 匯出測試。
```

### Pruned Paths

```text
- 不新增 /api/export-csv。
  原因：前端已有 filteredRows。

- 不引入 csv 套件。
  原因：欄位固定且需求簡單。

- 不重構 DataTable 資料流。
  原因：目標只需要讀取現有 filteredRows。
```

這個例子裡，Slime Coding 的重點不是「CSV 怎麼寫」。  
重點是：AI 沒有理由新增後端、套件或重構資料流。

---

## 13. 最短版檢查表

實作前：

```text
[ ] Food Points 已列出。
[ ] Goal Frontier 已列出。
[ ] Start Frontier 已由 repo evidence 支持。
[ ] Meeting Corridor 已定義。
[ ] Forbidden Changes 已列出。
[ ] Stop Condition 已列出。
```

實作中：

```text
[ ] 每個 touched file 都在 corridor 內。
[ ] 每個新增函式都能回指到 food point。
[ ] 沒有新增 corridor 外依賴。
[ ] 沒有 corridor 外重構。
[ ] 被剪掉的路徑沒有復活。
```

實作後：

```text
[ ] Food Points 已滿足。
[ ] Stop Condition 已成立。
[ ] 測試或檢查已執行。
[ ] 未覆蓋風險已列出。
[ ] 若失敗，Pruned Paths 已補登。
```

---

## 14. 收束句

Slime Coding 不是要讓 AI 變成黏菌。  
Slime Coding 是把黏菌的「探索、強化、萎縮」與雙向導航的「起點、終點、交會」轉成 coding 紀律。

它的核心價值是：

```text
把 AI 的創造力限制在交會走廊裡。
讓 evidence 決定哪條路變粗。
讓 stop condition 決定何時停手。
```

最短句：

> 先長前沿，再接走廊；只改走廊，達標就停。
