# Coding Agent Guardrails

[English](README.md)

**安裝一次，之後照常要求 coding agent 工作。**

Guardrails 會限制 agent 的修改路徑，在 Stop 自動執行可信檢查、記錄最終
狀態，並只產生一個 review artifact：`.guardrails/review.json`。使用者不必
編輯 corridor、不必選 Rigor、不必填 Evidence、不必執行 Agentcam 指令，
也不必把五行交接單貼進 PR。

## 為什麼會有一套限制 vibe 的工具

這個專案主要靠 coding agent 實作。我不是軟體工程師，不會寫 code，也沒有能力
逐行判斷 diff。實際上，我通常不細看：benchmark 漂亮、工具能跑起來、遊戲會動，
我就會覺得它大概可以往前走。

這就是這個工具包的出發點。我自己也是散散地在用這套工具，甚至不一定會
完整跑完它設計的流程。這聽起來很荒謬：我糊裡糊塗地 vibe 出了一套限制 vibe 的工具。
荒謬感是真的，問題也是真的。當 coding agent 快速產出大量 code，
真正的風險常常落在交接流程：到底改了什麼、檢查有沒有真的跑、下一個人接不接得了手。
這裡的每個工具都在做同一件事：把「相信我」換成「有紀錄的事實」。

一般任務只有原本的流程：

```text
要求 agent 修改
→ agent 工作
→ Stop 自動檢查範圍、測試、風險與最終狀態
→ 照原本習慣要求 agent commit 或開 PR
```

只有客觀上屬於高風險的變更，Stop 才會多要求一次精確回覆，例如：
`確認高風險變更 7F3A2C`。這個 nonce 綁定當下的產品狀態；之後再修改任何
產品檔案，確認就會失效。

## 安裝

```bash
git clone https://github.com/shihchengwei-lab/coding-agent-guardrails ~/guardrails
~/guardrails/install.sh /path/to/your/project
```

```powershell
git clone https://github.com/shihchengwei-lab/coding-agent-guardrails $HOME\guardrails
& $HOME\guardrails\install.ps1 -Project C:\path\to\your\project
```

目標必須是 Git worktree 根目錄，並需要 Python 3.11+。安裝器會在
`<git-dir>/guardrails/` 建立版本化 runtime，為 Claude Code 與 Codex 接上
同一個 coordinator hook，並在 repo 根目錄建立 `guardrails` launcher。
安裝完成後，原本的 toolkit clone 可以搬走或刪除。

若 repo 根目錄只有一種明確的測試生態，安裝器會自動設定 primary check：
pytest、Node、Cargo、Go 或 Flutter。若無法可靠判斷，只執行
`git diff --check`，並誠實標示 `structural-only`；不猜命令，也不假裝測試
已通過。

既有使用者 hooks 與 trusted checks 會保留。舊 `.slime/` 只保留成 archived
state，runtime 不再讀取。只有能證明是 installer 管理的內容才會更新；自訂
內容會保留並警告。

## 工具自動做什麼

第一次修改產品檔案前，受管理的 agent instruction 會讓 agent 把可觀察結果
與預計路徑存進 Git-local state，不進 working tree。Direct edit 在寫入前檢查；
shell 的副作用只能在命令完成後立即偵測，並於 Stop 再檢查一次。

Stop 由單一 coordinator 依序執行一次：

1. 計算整個 branch delivery 的變更，排除未被本次工作改動的既有 dirty state。
2. 確認所有產品檔案都在 agent 事前宣告的範圍內。
3. 執行 `git diff --check` 與已設定的 trusted checks。
4. 依路徑、檔案狀態、dependency 變更與 Agentcam 訊號推導風險。
5. 高風險時要求綁定目前狀態的確認。
6. 完成 Agentcam 本機實錄，原子寫入 `.guardrails/review.json`。

Artifact 記錄變更檔案、範圍擴張、檢查結果、風險、capture coverage 與產品
fingerprint。工具不會自動 stage、commit、push、開 PR 或 merge。當你原本就
要求 agent commit 或開 PR 時，managed instruction 才會要求它一併納入 artifact。

Corridor CI 只讀 artifact；PR 內文可以自由寫。它會獨立重算 PR 的產品狀態、
scope coverage、風險下限與 recorded check 綁定。Dependency 或 workflow 變更
仍需目前 head SHA 的 GitHub approval；使用者完成高風險確認後，agent 可以在
PR 建立後同步該留言。

## 心智模型

你只需要掌握兩個概念：agent 在第一次編輯前**宣告範圍**；遇到高風險變更時，
由你**輸入確認短語**。其餘的一切——turn、delivery、指紋、artifact 的內部
結構——都是 hooks 替你運轉的機器；當它擋下你時，會說明原因和下一步。

兩層機制各司其職。review artifact 是作者自己的證據：它讓誠實的 agent 保持
誠實、給 reviewer 一個入口，但它由作者控制。真正的安全邊界在別處——綁定
head SHA 的 GitHub 審批留言、base branch 的 policy gate，以及最終 agent
執行時的 OS 權限。

## 使用者可能會操作的命令

這些是進階維護，不是日常步驟：

```bash
./guardrails doctor
./guardrails doctor --remote
./guardrails check set primary -- python -m pytest -q
./guardrails check remove primary
./guardrails uninstall --dry-run
./guardrails uninstall
./guardrails uninstall --purge-state  # 連保留的本機歷史與設定一併移除
```

若 host hook 無法提供使用者原始 prompt，唯一 fallback 是
`guardrails approve <nonce>`。它要求互動式 TTY，且人類必須重新輸入完整確認
語句；非互動 agent shell 不能自行批准。

## 做不到的事

- Hook 不是 filesystem sandbox。Direct edit 是寫入前阻擋；shell 是寫入後
  偵測。真正的硬邊界仍是 OS 權限或 sandbox。
- Review artifact 是與最終狀態綁定的作者端本機證據，不是第三方 attestation。
- `structural-only` 代表找不到可靠測試命令，不代表功能正確。
- 工具不能判斷產品品質，也不能取代人工 review。
- Workflow 存在不等於 merge gate；repo ruleset 仍須把 `Policy Gate`、
  `Corridor` 與相關測試設為 required checks。
- 信任模型處理誤操作、漂移與 PR 自改政策，不對抗擁有完整本機與 GitHub
  管理權限的惡意管理者。

Breaking upgrade 請看[遷移指南](docs/MIGRATION.md)。各元件說明：
[Agentcam](agentcam/)、[Slime coordinator](slime-coding/)、
[Corridor CI](corridor-ci/) 與 [kiss-my-diff](kiss-my-diff/)。

## 版本

最低摩擦版本線是 Agentcam `0.7.0` 與 Corridor CI `v15.0.0`。Release tag 分別
是 `agentcam-v0.7.0` 與 `corridor-ci-v15.0.0`。安裝器產生的 workflow 會 pin
這個已發布且不可變的 Corridor 版本。跨元件變更記錄在
[CHANGELOG.md](CHANGELOG.md)。

## 授權

MIT。
