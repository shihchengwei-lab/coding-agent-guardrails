# Benchmark Results

## 一句話結論

現在的 AI 多半已經能完成小型 coding 任務；`AGENT.md` 的主要價值不是提高「能不能過測」，而是降低繞路、偏離既有寫法、漏用既有 helper、改太多檔案這類工程紀律問題。

## 測試設計

- 任務池：18 個自然 bugfix 任務。
- 模型：`gpt-5.5`、`gpt-5.4`、`gpt-5.4-mini`、`gpt-5.3-codex-spark`。
- 分組：
  - `baseline`：只給一般 bug report。
  - `disciplined`：同樣 bug report，加上 repo 內的 `AGENT.md`。
- 總 runs：144 次，來自 `4 models x 2 variants x 18 tasks`。
- Prompt 特性：沒有 future-feature bait，沒有明講不要加依賴，沒有明講不要重構，也沒有暴露評分規則。

## 核心結果

| model | baseline avg | disciplined avg | quality change | patch size change |
| --- | ---: | ---: | ---: | ---: |
| `gpt-5.3-codex-spark` | 92.92 | 98.82 | +27.78 | -0.23 lines |
| `gpt-5.4-mini` | 96.74 | 98.89 | +5.55 | -1.22 lines |
| `gpt-5.5` | 99.93 | 100.00 | +0.00 | -0.78 lines |
| `gpt-5.4` | 100.00 | 99.86 | +0.00 | +0.06 lines |

所有 144 次都通過測試，所以「pass rate」不是有差異的指標。真正有差的是 quality、scope、simplicity 和平均 patch size。

## 這代表什麼

`AGENT.md` 對弱一點或快一點的模型效果最明顯。`gpt-5.3-codex-spark` 的 baseline 雖然都能過測，但常見問題是沒有沿用既有 helper、修法不夠貼近原本設計，quality 從 72.22 拉到 100.00。

`gpt-5.4-mini` 也有可見改善：總分提高、quality 提高，而且平均 patch 變小。這比較貼近「AI 會寫出能跑但有點繞」的體感。

強模型本來就接近滿分，所以 `AGENT.md` 的邊際效果小。`gpt-5.5` 主要改善在 patch 更小；`gpt-5.4` 則是 baseline 已滿分，discipline 組只有一次小扣分，這比較像單次 noise。

## 這沒有證明什麼

- 沒有證明 `AGENT.md` 會讓模型更會修 bug；這輪所有模型本來都修得過。
- 沒有測出依賴膨脹；這 18 題裡沒有任何 dependency incident。
- 沒有覆蓋大型 repo、模糊需求、多檔重構、前端 UI、資料庫 migration、第三方 API 這類更容易繞路的場景。
- 目前每個 model/variant/task 只跑一次，還不能估計 run-to-run variance。

## 可採用說法

比較保守但符合數據的說法：

> 在這組自然 bugfix benchmark 裡，`AGENT.md` 不影響任務是否完成，因為所有 runs 都通過測試；它主要改善工程紀律，尤其是較弱或較快模型的 helper reuse、修改範圍和 patch 克制度。

更短的 repo 定位：

> A tiny `AGENT.md` discipline file for coding agents. It does not teach agents to pass tests; it nudges them to shave off unnecessary abstraction, scope, and ceremony.

## 詳細報告

完整數據和 non-perfect runs 在：

- `bench/results/2026-06-22-natural-v2-expanded-benchmark.md`

原始 runs 保留在：

- `bench/runs-natural-v2/`
