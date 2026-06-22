# Benchmark Results

## 一句話結論

現在的 AI 多半已經能完成小型 coding 任務；`AGENT.md` 的價值不在提高「能不能過測」，而是在嘗試降低繞路、偏離既有寫法、漏用既有 helper、改太多檔案這類工程紀律問題。

7 行版太短，效果變得不穩；完整版效果最好，但比較像 checklist。最新 sweet-spot search 顯示：目前最適合放在 repo 首頁的是 10 行 balanced 版。

## 目前推薦版本

```text
Build only what is needed now.
Prefer the smallest readable change.
Read the existing code before editing.
Use existing helpers and patterns before adding new code.
Use built-ins before adding dependencies.
Touch the fewest files needed.
Do not add abstractions for one-shot code.
Preserve existing behavior unless asked to change it.
Verify with the smallest relevant test.
Stop when done.
```

## 核心比較

| version | avg total | avg quality | avg line delta |
| --- | ---: | ---: | ---: |
| 7-line | 98.37 | 93.05 | 5.56 |
| 10-line balanced | 98.92 | 97.22 | 5.69 |
| 10-line helper-explicit | 98.80 | 94.44 | 5.16 |
| longer original | 99.39 | 98.61 | 5.17 |

完整版仍是 benchmark 最強；10 行 balanced 版不是最高分，但它在可讀性和效果之間比較平衡。它比 7 行版穩，quality 接近完整版，又不需要回到長清單。

## 重要限制

不要把這張表當成模型能力排行。這份 benchmark 測的是 coding discipline，例如是否沿用既有 helper、是否少改檔案、是否避免不必要抽象。強模型如果寫出等價 inline 修法，仍可能在 quality check 上輸給剛好用了 helper 的弱模型。

目前每個 model/variant/task 只跑一次，還不能估計 run-to-run variance。

## 可採用說法

> `AGENT.md` 不會讓模型更會完成小型 bugfix；這些模型本來就能過測。它的價值是當模型已經能完成任務時，提醒它用更局部、更符合既有程式碼的修法。

> 7 行版比較像漂亮標語；完整版比較像操作 checklist；10 行 balanced 版是目前比較好的折衷。

## 詳細報告

Sweet-spot search:

- `bench/results/2026-06-22-sweet-spot-search.md`

7 行版重跑報告：

- `bench/results/2026-06-22-slim-agent-rerun-benchmark.md`

歷史長版 `AGENT.md` 報告：

- `bench/results/2026-06-22-natural-v2-expanded-benchmark.md`
