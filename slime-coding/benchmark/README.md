# Benchmark

這個資料夾放的是 Slime Coding 的公開跑分資料，不是新的 runner。

定位要講準：這是一組乾淨、誠實、可公開的 directional benchmark，也是一個 2026-06-29 的 dated snapshot。模型、Claude Code harness、Ponytail、Slime Coding 和題庫都可能隨時間漂移；這裡的數字可以說明這組任務裡的 trade-off，但不能被讀成穩定常數，也不能證明所有 repo、所有模型、所有任務都會得到同樣結果。

## 測什麼

- 題庫：Ponytail-derived task pool
- 來源 repo：[DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail)
- Ponytail commit：`c4d1925`
- 模型：`claude-haiku-4-5-20251001`
- 日期：2026-06-29
- 題目：19 題
- 組別：`baseline`、`ponytail`、`slime-coding`（strict corridor default）
- 次數：每題每組 4 次
- 有效樣本：228 cells

題目分成兩類：

- `safety`：7 題，檢查模型會不會改壞安全或行為邊界。
- `feature`：12 題，檢查模型能不能完成較像產品功能的任務，以及 diff 會不會變大。

## 結果摘要

全部 19 題：

| 組別 | 通過 | touched files | 總 LOC | vs baseline LOC | 平均 cost | 平均 tokens | 平均時間 |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 69/76 = 90.8% | 115 | 5744 | baseline | $0.0897 | 331k | 49.8s |
| ponytail | 72/76 = 94.7% | 147 | 5055 | -12.0% | $0.1047 | 299k | 55.6s |
| slime-coding | 76/76 = 100.0% | 107 | 4351 | -24.3% | $0.1223 | 478k | 76.6s |

Feature 12 題：

| 組別 | 通過 | touched files | 總 LOC | vs baseline LOC | 平均 cost | 平均 tokens | 平均時間 |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 41/48 = 85.4% | 87 | 5364 | baseline | $0.1173 | 454k | 65.9s |
| ponytail | 44/48 = 91.7% | 81 | 4426 | -17.5% | $0.1059 | 391k | 57.0s |
| slime-coding | 48/48 = 100.0% | 76 | 4010 | -25.2% | $0.1465 | 585k | 91.0s |

Safety 7 題：

| 組別 | 通過 | touched files | 總 LOC | vs baseline LOC | 平均 cost | 平均 tokens | 平均時間 |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 28/28 = 100.0% | 28 | 380 | baseline | $0.0425 | 121k | 22.1s |
| ponytail | 28/28 = 100.0% | 66 | 629 | +65.5% | $0.1027 | 141k | 53.2s |
| slime-coding | 28/28 = 100.0% | 31 | 341 | -10.3% | $0.0809 | 295k | 51.8s |

## 怎麼讀

Slime Coding 在這組任務裡：

- 通過率比 baseline 高 9.2 percentage points。
- touched files 比 baseline 少 7.0%，比 Ponytail 少 27.2%。
- 總 LOC 比 baseline 少 24.3%，比 Ponytail 少 13.9%。
- 平均 cost 比 baseline 高 36.3%，比 Ponytail 高 16.8%。
- 平均 tokens 比 baseline 高 44.3%，比 Ponytail 高 59.8%。
- 平均時間比 baseline 高 53.8%，比 Ponytail 高 37.7%。

所以這不是「Slime 免費變好」。比較準確的讀法是：

> Slime Coding 用更多推理成本，換到較高完成率、較少 touched files 與較小 diff；Ponytail 更省 token、更快、更便宜。

## 資料檔

- [`summary.json`](summary.json)：總表、分組總表、delta、資料清理規則。
- [`by-task.csv`](by-task.csv)：每題每組的 4 次聚合。
- [`cells.csv`](cells.csv)：228 個有效 cell 的逐筆資料。

## 清理規則

這輪結果有做資料清理，但規則事先固定，不挑好看的分數：

- Claude 429 / session limit cell 不算模型失敗，重跑。
- Baseline timeout cell 不算模型效果，重跑。
- 舊的 report-only Slime rows 已由 strict corridor default run 取代，因為 strict 現在是預設行為。
- strict run 實際跑到較大的本地 Ponytail 題池；這裡只納入與 baseline / Ponytail 同口徑的 19 題。

最後三組都是 76/76 個有效樣本，沒有 missing cost/token。

## 限制

- 這是 Haiku 單一模型，不代表 Sonnet、Opus 或其他供應商。
- 這是 Ponytail-derived task pool，不代表所有真實產品 repo。
- 這裡放結果資料，不放完整 runner 與 fixture；可重現性依賴 Ponytail 原 repo 與本地 Claude Code 環境。
