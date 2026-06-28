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
- 組別：`baseline`、`ponytail`、`slime-coding`
- 次數：每題每組 4 次
- 有效樣本：228 cells

題目分成兩類：

- `safety`：7 題，檢查模型會不會改壞安全或行為邊界。
- `feature`：12 題，檢查模型能不能完成較像產品功能的任務，以及 diff 會不會變大。

## 結果摘要

全部 19 題：

| 組別 | 通過 | 總 LOC | vs baseline LOC | 平均 cost | 平均 tokens | 平均時間 |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 69/76 = 90.8% | 5744 | baseline | $0.0897 | 331k | 49.8s |
| ponytail | 72/76 = 94.7% | 5055 | -12.0% | $0.1047 | 299k | 55.6s |
| slime-coding | 74/76 = 97.4% | 4544 | -20.9% | $0.1159 | 465k | 69.9s |

Feature 12 題：

| 組別 | 通過 | 總 LOC | vs baseline LOC | 平均 cost | 平均 tokens | 平均時間 |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 41/48 = 85.4% | 5364 | baseline | $0.1173 | 454k | 65.9s |
| ponytail | 44/48 = 91.7% | 4426 | -17.5% | $0.1059 | 391k | 57.0s |
| slime-coding | 47/48 = 97.9% | 4169 | -22.3% | $0.1397 | 574k | 84.8s |

Safety 7 題：

| 組別 | 通過 | 總 LOC | vs baseline LOC | 平均 cost | 平均 tokens | 平均時間 |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 28/28 = 100.0% | 380 | baseline | $0.0425 | 121k | 22.1s |
| ponytail | 28/28 = 100.0% | 629 | +65.5% | $0.1027 | 141k | 53.2s |
| slime-coding | 27/28 = 96.4% | 375 | -1.3% | $0.0751 | 278k | 44.3s |

## 怎麼讀

Slime Coding 在這組任務裡：

- 通過率比 baseline 高 6.6 percentage points。
- 總 LOC 比 baseline 少 20.9%。
- 平均 cost 比 baseline 高 29.2%。
- 平均 tokens 比 baseline 高 40.2%。
- 平均時間比 baseline 高 40.3%。
- `cache` safety 題有 1 次失敗：它把 `lru_cache` 放在仍會增加 `_calls` 的位置，行為檢查沒有過。

所以這不是「Slime 免費變好」。比較準確的讀法是：

> Slime Coding 用更多推理成本，換到較高完成率與較小 diff，但它仍可能引入 safety regression。

## 資料檔

- [`summary.json`](summary.json)：總表、分組總表、delta、資料清理規則。
- [`by-task.csv`](by-task.csv)：每題每組的 4 次聚合。
- [`cells.csv`](cells.csv)：228 個有效 cell 的逐筆資料。

## 清理規則

這輪結果有做資料清理，但規則事先固定，不挑好看的分數：

- Claude 429 / session limit cell 不算模型失敗，重跑。
- Baseline timeout cell 不算模型效果，重跑。
- Slime 的 `cache` safety 失敗保留，因為那是有效任務失敗。

最後三組都是 76/76 個有效樣本，沒有 missing cost/token。

## 限制

- 這是 Haiku 單一模型，不代表 Sonnet、Opus 或其他供應商。
- 這是 Ponytail-derived task pool，不代表所有真實產品 repo。
- 這裡放結果資料，不放完整 runner 與 fixture；可重現性依賴 Ponytail 原 repo 與本地 Claude Code 環境。
