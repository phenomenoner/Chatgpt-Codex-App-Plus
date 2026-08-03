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
- 長跑省回合：本機 supervisor 負責 heartbeat、停滯判定與終態喚醒，減少高脈絡輪詢。
- 分工有煞車：需要 subagent 時先做成本、獨立性與寫入所有權判斷。
- 設定可重現：提供安全預設、全域 `AGENTS.md` 範例與可選安裝器。
- 同步不洩密：只有 manifest allow-list 內的檔案能進 repo；任何憑證、私有路徑或未知檔案都會 fail closed。

## 內容

| Component | 解決什麼問題 | 發佈方式 |
|---|---|---|
| `batch-complete-independent-review` | blocker 批次完整度、counterfactual fixed-point review、hash-bound verdict | 內含 |
| `long-run-supervisor` | 長時間命令的低成本監督與 wake-only 回報 | 內含 |
| `codex-cli-luna-worker` | 在原生協作介面沒有 Luna 時，以唯讀 patch worker 補位 | 內含 |
| `completeness-and-test-synthesis` | 防止「測試綠了但功能仍不完整」 | 內含 |
| `incident-to-regression` | 把事故轉成可重播、可驗證的 regression package | 內含 |
| `claude-independent-review` | 明示授權後，以 Claude CLI 做獨立、hash-bound review | 內含、選配 |
| `operate-a2a-superhub` | A2A Superhub 的 bounded operation 與診斷流程 | 內含、選配 |
| `baton-fanout-skill` | subagent dispatch brake 與 ownership contract | [上游 pointer](https://github.com/phenomenoner/baton-fanout-skill) |
| Understand Anything | codebase knowledge graph 與理解工具 | [上游 pointer](https://github.com/Egonex-AI/Understand-Anything) |
| OpenAI skills | 官方與 curated skills | [上游 pointer](https://github.com/openai/skills) |

完整需求、成熟度與來源請看 [component catalog](catalog/components.json)。已有 canonical public repo 的項目不重複 vendoring，以避免授權混淆與 fork 漂移。

## 快速開始

```powershell
git clone https://github.com/phenomenoner/Chatgpt-Codex-App-Plus.git
Set-Location Chatgpt-Codex-App-Plus
python scripts/public_sync.py validate
```

先預覽推薦 skills 的安裝位置與動作：

```powershell
pwsh -File scripts/install.ps1 -WhatIf
```

確認後安裝推薦組合，或只安裝指定 skill：

```powershell
pwsh -File scripts/install.ps1
pwsh -File scripts/install.ps1 -Skill long-run-supervisor,batch-complete-independent-review
```

Codex 目前會從 user-level `.agents/skills`、repo-level `.agents/skills` 與系統位置載入 skills；如新增 skill 後未立即出現，重啟 Codex。詳見官方 [Build skills](https://learn.chatgpt.com/docs/build-skills)。

## 安全設定先行

`config/config.example.toml` 採 `workspace-write`＋`on-request`，不把個人的 full-access 設定包裝成公開 quick start。`config/AGENTS.example.md` 則把最小充分測試、review fixed point、Baton 與公開 hygiene 組成可選的全域規則範例。

Codex 的 personal config、project config 與命令列 override 有明確優先序；複製設定前請先閱讀官方 [Config basics](https://learn.chatgpt.com/docs/config-file/config-basic)。

## 為什麼同步器是 fail closed

`scripts/public_sync.py` 不會掃描或鏡像整個 Codex home。它只接受 [public source manifest](manifest/public-sources.json) 內逐項核准的來源，並且：

1. 拒絕 source/destination path escape、symlink、binary、backup 與 runtime-state 檔案。
2. 拒絕個人絕對路徑、token、secret assignment 與 private runtime 訊號。
3. 將文字正規化為 UTF-8/LF，再生成逐檔 SHA-256 lock。
4. 對少數非機密但容易誤判的字串，只允許 manifest 內逐檔、逐 finding、附理由的例外。
5. 任何新檔都必須先人工加入 allow-list；自動化不得自行擴權。

架構與 threat model 見 [docs/architecture.md](docs/architecture.md)，每週同步契約見 [docs/weekly-sync.md](docs/weekly-sync.md)。

## 專案定位

這個 repo 現階段是可直接安裝的 skill/tool collection，不宣稱已是官方 plugin。Codex 官方建議：skill 用來描述可重用 workflow；需要把多個 skills、connectors 或 MCP surface 做成安裝式 bundle 時，再包成 plugin。等這套 collection 的 public API 穩定後，再評估 marketplace-ready plugin，而不是提早鎖死結構。

## License

本 repo 自有內容採 [MIT License](LICENSE)。Pointer 指向的第三方或上游內容仍適用各自的授權；本 repo 不重新授權那些內容。詳見 [NOTICE.md](NOTICE.md)。
