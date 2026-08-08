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

- 一次找齊：reviewer 發現第一個 blocker 後不停止，持續做到 coverage closure。
- 長任務接得回來：Context Canvas 把當前 session 身分、可明示延續的 semantic task lineage，以及依 sanitization policy 保存的歷史 tool snapshots 分開；重開時不再因 goal 換個說法就把工作卡死。
- 長跑省回合：本機 supervisor 負責 heartbeat、停滯判定與終態喚醒，減少高脈絡輪詢。
- 分工有煞車：需要 subagent 時先做成本、獨立性與寫入所有權判斷。
- 設定可重現：提供安全預設、全域 `AGENTS.md` 範例與可選安裝器。
- 同步不洩密：只有 manifest allow-list 內的檔案能進 repo；任何憑證、私有路徑或未知檔案都會 fail closed。

## 內容

| Component | 解決什麼問題 | 發佈方式 |
|---|---|---|
| `context-canvas-codex` | 本機 semantic task lineage、跨 session 明示延續、最近任務／snapshot 篩選查找、hash-bound evidence，以及 content-addressed、deduplicated、TTL/pin 管理的 sanitized tool snapshots | 內含 plugin、選配 |
| `batch-complete-independent-review` | ordinary review 一次找完整 finding batch；明示獨立／release gate 才啟用 fixed-point 與 hash-bound verdict | 內含 |
| `long-run-supervisor` | 長時間命令的低成本監督與 wake-only 回報 | 內含 |
| `codex-cli-luna-worker` | 在原生協作介面沒有 Luna 時，以唯讀 patch worker 補位 | 內含 |
| `completeness-and-test-synthesis` | 依實際 failure seam 選最低可否證的測試高度，處理 readiness 與「測試綠了但實際仍壞」 | 內含 |
| `incident-to-regression` | 把事故轉成可重播、可驗證的 regression package | 內含 |
| `claude-independent-review` | 明示授權後，以 Claude CLI 做獨立、hash-bound review | 內含、選配 |
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
收到 opaque ID，代表這個版本有載入 `UserPromptSubmit`；再開一個全新 task，重驗
`SessionStart` ID，並做一次 harmless tool call，確認 `_snapshots/events` 出現新的 manifest。
Codex CLI 0.146.0 的先前本機實測是
plugin MCP/skill 會載入、plugin-bundled hook 卻未執行；這個顯式 installer
就是相容層，並會保留既有 hooks 與 hash-addressed backup。安裝、catalog
discovery 或 tool call 顯示 `started` 都不等於實際執行完成。

先預覽推薦 skills 的安裝位置與動作：

```powershell
pwsh -File scripts/install.ps1 -WhatIf
```

確認後安裝推薦組合，或只安裝指定 skill：

```powershell
pwsh -File scripts/install.ps1
pwsh -File scripts/install.ps1 -Skill long-run-supervisor,batch-complete-independent-review
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

0.4 先把三件事拆開：hook-derived opaque ID 只代表目前 execution；semantic map 以 lineage 保存；tool result 則留在 snapshot cache。錯過 startup hook 時，後續 `UserPromptSubmit` 可補回目前 ID。`canvas_start` 對同 ID 的文字差異只回報 conflict、不覆寫也不阻塞；跨 session 要用 `canvas_continue` 明示前身，後繼會保存 stable lineage 與 canonical predecessor SHA-256。Goal 只有 active/completed/abandoned，卡點另建 blocker node。`canvas_list --limit 8` 依最近更新列出前後繼、blocker 數與可否延續，不用再拿 opaque ID 猜時間順序。

保存面不把「完整 tool result」和「建立 semantic node」綁在一起。對 Codex 實際送出的、已 opt-in `PostToolUse` callback payload，會保存 hook 收到的完整 model-facing payload（依宣告 policy sanitization，超過上限則整筆跳過而不截斷），以 SHA-256＋deterministic gzip 做 dedupe。Sanitizer 會用同一套 suffix-aware 規則處理 structured key、文字 assignment、percent/form query key、bracket/index notation、JSON Unicode escape 與 escaped wrapper；任何 malformed-percent assignment key 都採保守遮罩，而且前面已找到一個值也不會停止後續 encoded／escaped representation passes，但仍保留相鄰的安全 query parameters。支援的 base64／percent-encoded textual data URL（含未加引號的 MIME parameters）會 canonicalize、decode、redact；不能安全解析的 `data:` 會讓整筆 observation 不落盤。其他圖片、影音與任意 binary 會原樣保存並明示標成 `opaque-uninspected`，不是已掃過 secret 的 sealed raw evidence。一般 snapshot 預設 14 天 TTL，GC 會重算 journal plan ID、驗證唯一且有序的 event/object/blob identities，再從目前已驗證狀態決定中斷後剩餘工作；被 finding／decision／verification 引用時，會先驗證所有 transitive blobs 再 pin。`snapshot_list` 可依 tool、capture status、pin state 與 cursor 分頁；body 仍不進 Canvas search、lifecycle injection、closeout 或 MCP 回應，完整回查只能用明示 CLI export。

目前 Codex 會在支援的 handler 回傳已 opt-in post-tool payload 時呼叫 `PostToolUse`；Bash 即使 non-zero exit 仍可能有 callback 與 exit metadata 可保存。若 dispatch／handler failure 沒產生 callback payload，就不會進 archive，而且此 adapter 沒有另一個 failure sibling 可補抓。安裝後應在全新 task 做 harmless tool call，實際檢查新 manifest；不能只看 plugin catalog 或設定檔就推論 capture 已生效。

repo 內附 machine-readable benchmark，涵蓋 persistent MCP read、fresh CLI、首次 snapshot write、warm dedupe、manifest read、exact GC preview，以及 cold small／large `PostToolUse` hook。GC 會驗證 event/object/blob graph 並找出 orphan，不能拿只計數的舊 preview 直接相比；數字也會受 Python、ACL、儲存、防毒、同機負載與 payload shape 影響。比較或發布結果時，必須連同同一 receipt 的 executable hashes 與環境一起看。

非互動 CLI 若採 `approval_policy = "never"`，需要核准的 MCP call 會被取消，
不是自動放行。驗收時必須明確設定已審過的 plugin-scoped MCP approval
policy，並以 `completed` tool receipt 加 canonical JSON readback 判定；詳見
[技術說明](docs/context-canvas-codex.md)。

這個 repo 現在同時提供可直接安裝的 skills/tools 與第一個 marketplace-ready community plugin。它不是 OpenAI 官方 plugin；repo marketplace 只是讓來源、版本與安裝路徑可檢查、可重現。

## License

本 repo 自有內容採 [MIT License](LICENSE)。Pointer 指向的第三方或上游內容仍適用各自的授權；本 repo 不重新授權那些內容。詳見 [NOTICE.md](NOTICE.md)。
