# Benchmark Results

## 一句話結論

現在的 AI 多半已經能完成小型 coding 任務；`AGENT.md` 的價值不在提高「能不能過測」，而是在嘗試降低繞路、偏離既有寫法、漏用既有 helper、改太多檔案這類工程紀律問題。

新版 7 行 `AGENT.md` 重跑後，結果變成 mixed：它仍然是低成本 discipline nudge，但這一輪不能再說它對所有模型都穩定有效。

## 測試設計

- 任務池：18 個自然 bugfix 任務。
- 模型：`gpt-5.5`、`gpt-5.4`、`gpt-5.4-mini`、`gpt-5.3-codex-spark`。
- 分組：
  - `baseline`：只給一般 bug report。
  - `disciplined`：同樣 bug report，加上 repo 內的 7 行 `AGENT.md`。
- 總 runs：144 次，來自 `4 models x 2 variants x 18 tasks`。
- Prompt 特性：沒有 future-feature bait，沒有明講不要加依賴，沒有明講不要重構，也沒有暴露評分規則。

## 最新核心結果

| model | baseline avg | disciplined avg | quality change | patch size change |
| --- | ---: | ---: | ---: | ---: |
| `gpt-5.3-codex-spark` | 98.82 | 97.64 | -5.56 | +0.17 lines |
| `gpt-5.4` | 93.19 | 99.86 | +33.33 | +0.39 lines |
| `gpt-5.4-mini` | 97.85 | 97.43 | -5.56 | -0.56 lines |
| `gpt-5.5` | 98.82 | 98.54 | +0.00 | +0.22 lines |

所有 144 次都通過測試，沒有 dependency incident。也就是說，這組 benchmark 測到的仍然不是「會不會完成任務」，而是「完成時是否更貼近既有程式碼、更少繞路」。

不要把這張表當成模型能力排行。這次分數可能出現「弱模型 baseline 比強模型 baseline 高」，原因是 quality check 很二元：有用既有 helper 就給分，寫出等價 inline 修法也會被扣成 0。例如 `natural_coupon_case` 裡，`gpt-5.4 baseline` 寫了 `code.strip().upper()`，`spark baseline` 則呼叫既有的 `normalize_code()`；兩者都過測，但只有後者拿到 quality 分。

## 這代表什麼

`gpt-5.4` 在新版 7 行 discipline 下改善很明顯：總分從 93.19 到 99.86，quality 從 66.67 到 100.00。

但其他三個模型沒有同步改善：`spark`、`mini`、`gpt-5.5` 的 total delta 都是小幅負值。`mini` 的 patch size 有變小，但 quality 掉了。這代表 7 行版本的效果比舊長版更不穩，或者單次 run 的隨機波動還太大。

## 這沒有證明什麼

- 沒有證明 `AGENT.md` 會讓模型更會修 bug；這輪所有模型本來都修得過。
- 沒有測出依賴膨脹；這 18 題裡沒有任何 dependency incident。
- 沒有覆蓋大型 repo、模糊需求、多檔重構、前端 UI、資料庫 migration、第三方 API 這類更容易繞路的場景。
- 目前每個 model/variant/task 只跑一次，還不能估計 run-to-run variance。

## 可採用說法

比較保守但符合最新數據的說法：

> 在這組自然 bugfix benchmark 裡，`AGENT.md` 不影響任務是否完成，因為所有 runs 都通過測試。新版 7 行 `AGENT.md` 對工程紀律的效果是模型相關且有噪音：對 `gpt-5.4` 很明顯，對其他三個模型這輪沒有穩定正效果。

再加一個重要限制：

> 這份 benchmark 可以比較同一模型內 baseline vs disciplined 的行為變化，但不適合拿來排序不同模型的能力。

更短的 repo 定位：

> A tiny `AGENT.md` discipline file for coding agents. It does not teach agents to pass tests; it asks them to shave off unnecessary abstraction, scope, and ceremony.

## 詳細報告

最新重跑報告：

- `bench/results/2026-06-22-slim-agent-rerun-benchmark.md`

歷史長版 `AGENT.md` 報告：

- `bench/results/2026-06-22-natural-v2-expanded-benchmark.md`

原始 runs 保留在本機但不進 git：

- `bench/runs-natural-slim/`
