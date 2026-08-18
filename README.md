<p align="center">
  <strong>ChatGPT Codex App Plus</strong><br>
  把好用的 Codex 客製化，變成可安裝、可驗證、可持續同步的公開工具箱。
</p>

<p align="center">
  <a href="README.md">繁體中文</a> · <a href="README.en.md">English</a> ·
  <a href="ABOUT.md">About</a> · <a href="SECURITY.md">Security</a>
</p>

<p align="center">
  <a href="https://github.com/phenomenoner/Chatgpt-Codex-App-Plus/actions"><img alt="CI" src="https://github.com/phenomenoner/Chatgpt-Codex-App-Plus/actions/workflows/ci.yml/badge.svg"></a>
  <a href="LICENSE"><img alt="MIT License" src="https://img.shields.io/badge/license-MIT-2ea44f.svg"></a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-3776ab.svg">
</p>

> 社群維護的獨立專案，並非 OpenAI、Anthropic 或其他上游專案的官方發行版。

## 30 秒看懂

Codex 很強，但真正順手的工作環境通常散落在個人設定、skills、PowerShell 工具與長期累積的操作規則裡。這個 repo 把其中可公開、可重用的部分整理成一套「Plus」層：

- 工程技能不分叉：review、長跑監督、驗證與 incident workflows 統一指向獨立的 canonical toolkit，不再維護第二份副本。
- Session 工作看得清楚：Context Canvas 把 hook transport identity、可選的任務地圖、明示 offload 的可回取 references，以及一次性 opt-in 歷史 snapshot 分開；缺少 Canvas 不會把原本可做的工作卡住。
- 分工有煞車：需要 subagent 時先做成本、獨立性與寫入所有權判斷。
- 設定可重現：提供安全預設、全域 `AGENTS.md` 範例與可選安裝器。
- 同步不洩密：只有 manifest allow-list 內的檔案能進 repo；任何憑證、私有路徑或未知檔案都會 fail closed。

## 內容

| Component | 解決什麼問題 | 發佈方式 |
|---|---|---|
| `context-canvas-codex` | 可選的 session 任務導航、跨 session 明示延續、可搜尋／分段回取的文字 references，以及 default-off、一次性 opt-in 的 sanitized tool snapshots | 內含 plugin、選配 |
| `smart-agentic-engineering-toolkit` | 16 個工程 skills，涵蓋 first-principles planning、specification、review、測試、delegation、recovery 與 release evidence | [canonical repo，版本鎖定 pointer](https://github.com/phenomenoner/smart-agentic-engineering-toolkit) |
| `operate-a2a-superhub` | A2A Superhub 的 bounded operation 與診斷流程 | 內含、選配 |
| `baton-fanout-skill` | Codex subagent dispatch brake、Luna/max bounded codegen route 與相對 working lane 的 review floor | [Codex 專用 branch](https://github.com/phenomenoner/baton-fanout-skill/tree/codex/add-model-effort-routing) |
| Understand Anything | codebase knowledge graph 與理解工具 | [上游 pointer](https://github.com/Egonex-AI/Understand-Anything) |
| OpenAI skills | 官方與 curated skills | [上游 pointer](https://github.com/openai/skills) |

完整需求、成熟度與來源請看 [component catalog](catalog/components.json)。已有 canonical public repo 的項目不重複 vendoring，以避免授權混淆與 fork 漂移。

Context Canvas 的 Hermes 對照、Codex 適配、安全邊界與可重跑效能量測整理在 [技術說明](docs/context-canvas-codex.md)。

## 快速開始

```powershell
git clone https://github.com/phenomenoner/Chatgpt-Codex-App-Plus.git
Set-Location Chatgpt-Codex-App-Plus
python scripts/public_sync.py validate
```

安裝 canonical Smart Agentic Engineering Toolkit：

```powershell
codex plugin marketplace add phenomenoner/smart-agentic-engineering-toolkit --ref v0.1.0
codex plugin add smart-agentic-engineering-toolkit@smart-agentic-engineering-toolkit
codex plugin list
```

安裝 Context Canvas plugin：

```powershell
codex plugin marketplace add phenomenoner/Chatgpt-Codex-App-Plus --ref main
codex plugin add context-canvas-codex@codex-app-plus
codex plugin list
```

先開一個新 task，確認模型真的收到該 task 的 opaque Context Canvas ID。
若只有 plugin／skill／MCP 出現、卻沒有新 ID，請從本 repo 根目錄安裝同一份
`SessionStart`＋`UserPromptSubmit`＋`PostToolUse` hooks 到 Codex 的 user config layer：

```powershell
python -I plugins/context-canvas-codex/scripts/install_context_canvas_hook.py install
python -I plugins/context-canvas-codex/scripts/install_context_canvas_hook.py check
```

接著在 Codex CLI 用 `/hooks` 檢查並信任三個定義。若目前 task 的下一個 prompt
收到 opaque ID，代表這個版本有載入 `UserPromptSubmit`；缺少 ID 只代表 Canvas
能力不可用，不會阻塞原任務。若要驗證 capture，再開一個全新 task 重驗
`SessionStart` ID，先用 `snapshot_capture_next` 指定下一個 harmless tool call，
再確認 `_snapshots/events` 出現且只出現該次 request 的新 manifest。
Codex CLI 0.146.0 的先前本機實測是
plugin MCP/skill 會載入、plugin-bundled hook 卻未執行；這個顯式 installer
就是相容層，並會保留既有 hooks 與 hash-addressed backup。安裝、catalog
discovery 或 tool call 顯示 `started` 都不等於實際執行完成。

本 repo 不再複製 general-engineering skills。若要安裝仍由這裡維護的選配
`operate-a2a-superhub`，先預覽安裝位置與動作：

```powershell
pwsh -File scripts/install.ps1 -Skill operate-a2a-superhub -WhatIf
```

確認後安裝：

```powershell
pwsh -File scripts/install.ps1 -Skill operate-a2a-superhub
```

Codex 目前會從 user-level `.agents/skills`、repo-level `.agents/skills` 與系統位置載入 skills；如新增 skill 後未立即出現，重啟 Codex。Plugin 則可同時包 skills、MCP server 與 lifecycle hooks。詳見官方 [Build skills](https://learn.chatgpt.com/docs/build-skills) 與 [Package plugins](https://developers.openai.com/plugins/build/plugins)。

## 安全設定先行

`config/config.example.toml` 採 `workspace-write`＋`on-request`，不把個人的 full-access 設定包裝成公開 quick start。`config/AGENTS.example.md` 則把最小充分測試、review fixed point、Baton 與公開 hygiene 組成可選的全域規則範例。

Codex 的 personal config、project config 與命令列 override 有明確優先序；複製設定前請先閱讀官方 [Config basics](https://learn.chatgpt.com/docs/config-file/config-basic)。

## 為什麼同步器是 fail closed

`scripts/public_sync.py` 不會掃描或鏡像整個 Codex home。它只接受 [public source manifest](manifest/public-sources.json) 內逐項核准的來源，並且：

1. 拒絕 source/destination path escape、symlink、binary、backup 與 runtime-state 檔案。
2. 拒絕個人絕對路徑、token、secret assignment 與 private runtime 訊號。
3. 將文字正規化為 UTF-8/LF，再生成逐檔 SHA-256 lock。
4. 對少數非機密但容易誤判的字串，只允許 manifest 內逐檔、逐 finding、附理由的例外。
5. 新來源、新 component 或擴大的 include pattern 必須先由人工修改 allow-list；既有核准 component 內的新檔仍須通過完整 public diff 檢閱，自動化不得自行擴權。

架構與 threat model 見 [docs/architecture.md](docs/architecture.md)，每週同步契約見 [docs/weekly-sync.md](docs/weekly-sync.md)。

## Context Canvas 的分層

0.5 把四件事拆開：hook-derived opaque ID 只是 Canvas transport provenance；session map 提供目標、決策、進度、依賴、阻塞與下一步導航；大型文字結果用 `reference_put/search/read/delete` 明示 offload 與分段回取；歷史 tool payload 只有先呼叫 `snapshot_capture_next` 才保存下一個匹配 callback。Canvas 不是 source of truth、授權系統、WAL、release gate 或 workflow engine，缺少 identity、map 或 lineage 不會阻塞工作。`canvas_start` 只在導航或 offload 有具體價值時建立；同 ID 的文字差異只回報 conflict、不覆寫，跨 session 延續仍用 `canvas_continue` 明示前身以保留 v3 相容性。

明示 reference 會先套用文字 redaction，再以 bounded UTF-8 chunks 原生回取；它是歷史資料，若要做 current-state claim 仍需重查 live source。Snapshot capture 預設關閉；armed request 有 expiry、只消耗一次、精確 tool mismatch 不會消耗，Canvas 自己的工具也會被忽略。匹配時保存 hook 收到的完整 model-facing payload（依宣告 policy sanitization，超過上限則整筆跳過而不截斷），並以 SHA-256＋deterministic gzip 做 dedupe。Sanitizer 與既有 TTL、pin、transitive blob 驗證及 GC 相容行為保留。`snapshot_list` 回傳 manifest；`snapshot_read(include_payload=true)` 可明示讀取 bounded chunks，完整本機檔案 export 仍走 CLI。

目前 Codex 會在支援的 handler 回傳已 opt-in post-tool payload 時呼叫 `PostToolUse`；這是 host transport surface，不是 Canvas 的自動保存規則。Bash 即使 non-zero exit 仍可能有 callback；dispatch／handler failure 若沒有 callback payload 就無法保存。安裝後應在全新 task 先 arm 一次 harmless exact tool call，再檢查新 manifest；不能只看 plugin catalog 或設定檔推論 capture 已生效。

repo 內附 machine-readable benchmark，涵蓋 persistent MCP read、fresh CLI、snapshot store write、warm dedupe、manifest read、exact GC preview，以及 cold small／large hook。直接 store-write 的量測不代表產品預設會 capture。GC 會驗證 event/object/blob graph 並找出 orphan；數字也會受 Python、ACL、儲存、防毒、同機負載與 payload shape 影響。

非互動 CLI 若採 `approval_policy = "never"`，需要核准的 MCP call 會被取消，
不是自動放行。驗收時必須明確設定已審過的 plugin-scoped MCP approval
policy，並以 `completed` tool receipt 加 canonical JSON readback 判定；詳見
[技術說明](docs/context-canvas-codex.md)。

這個 repo 現在提供可直接安裝的 Context Canvas community plugin、選配 A2A skill，以及指向 canonical engineering toolkit 的版本鎖定 pointer。它不是 OpenAI 官方 plugin；repo marketplace 只是讓來源、版本與安裝路徑可檢查、可重現。

## License

本 repo 自有內容採 [MIT License](LICENSE)。Pointer 指向的第三方或上游內容仍適用各自的授權；本 repo 不重新授權那些內容。詳見 [NOTICE.md](NOTICE.md)。
