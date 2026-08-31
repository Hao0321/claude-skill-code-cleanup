# Code Cleanup + Benchmark-Driven R&D

兩個可安裝到 Codex 或 Claude Code 的工程 Skills：

- `code-cleanup-helper`：read-only repository／Skill／release evaluator。
- `run-benchmark-driven-rd`：定義可證偽目標、保存 baseline、執行實驗、控制 promotion 與外部變更。

目前版本：**v0.21.0**。

## v0.21.0 重點

- Cleanup 每次 audit 都輸出下游目標的 D11 更新覆蓋：`managed`、`check-only`、`safe-auto-update`、`manual-only` 或 `no-origin`。檔案或 GitHub URL 存在不等於更新安全通過。
- R&D 對已授權、可分發的 Skill／軟體／遊戲／安裝器／release 開發，在 implementation／promotion／completion 階段預設納入安全更新能力與發布通道義務。
- 更新設計涵蓋來源驗證、staging、健康檢查、切換、回滾與安全淘汰 inactive 舊版；由套件／商店／部署平台管理的目標沿用原生更新機制。
- Task-aware Router v2、精簡 topic cards、精確 context budget 與 typed learning records，讓常用流程只載入必要規則，保留可重播證據。
- 完工 gate 不允許漏掉必要 capability，並保留 Cleanup 的 `REVIEW`／`NOT_CHECKED`，不把 route 選擇冒充功能驗證。

這兩個 Skill 是**開發與稽核流程**，不是背景 updater。安裝後不會自行掃描所有專案、執行排程或改寫程式；它們參與下游專案開發時，才會檢查與規劃該專案的更新功能，並在原始授權內實作。Audit-only／source-only 不因此取得修改、發布、簽章、背景常駐或刪除權限。

## 安裝

```bash
git clone https://github.com/Hao0321/claude-skill-code-cleanup.git
cd claude-skill-code-cleanup
python -m pip install -r requirements.txt
```

需要 Python **3.10+**。基本 Cleanup audit 使用標準函式庫；完整 self-test、learning gate 和精確 Token／topic-index 檢查需要 `requirements.txt` 中的 `tiktoken`。第一次使用 `o200k_base` 可能需要下載 tokenizer 資料；離線且沒有 cache 時會明確阻擋相關量測。

Codex 首次安裝（Windows PowerShell，在 clone 目錄內執行）：

```powershell
$skillRoot = Join-Path $env:USERPROFILE '.codex\skills'
foreach ($name in @('code-cleanup-helper', 'run-benchmark-driven-rd')) {
    if (Test-Path -LiteralPath (Join-Path $skillRoot $name)) {
        throw "$name 已存在；請先依下方升級流程比對，不要直接覆蓋。"
    }
}
New-Item -ItemType Directory -Force -Path $skillRoot | Out-Null
Copy-Item -Recurse -LiteralPath '.\code-cleanup-helper' -Destination $skillRoot
Copy-Item -Recurse -LiteralPath '.\run-benchmark-driven-rd' -Destination $skillRoot
```

Claude Code：把 `.codex\skills` 改成 `.claude\skills`。macOS／Linux 可將兩個資料夾複製到 `~/.codex/skills/` 或 `~/.claude/skills/`。使用自訂 `CODEX_HOME` 時，改用其 `skills` 目錄。兩個 Skill 應保持為相鄰資料夾，R&D 才能找到 Cleanup provider。重新啟動 host／開新 session 後使用新版。

Skill 文件中的「active private／canonical Skill」指你安裝後的本機權威版本，不需要存取作者的私人 repository。公開 checkout 可以用來執行本 repo 的驗證；日常使用以目前安裝的版本為準。

升級既有安裝：先更新 clone，再比對已安裝版本、備份個人修改與設定，僅同步這兩個 Skill 的已確認差異。不要對使用者工作樹自動 `git pull`、刪除自訂檔或用遞迴複製當成完整 updater。可把本 repo URL 交給 Codex／Claude Code，要求它在保留本機修改的前提下完成比對與升級；正在執行的 Skill 留到下一次 invocation／重啟才切換。

## 快速開始

```powershell
$env:PYTHONUTF8='1'

# read-only deterministic audit
python code-cleanup-helper/scripts/audit.py C:\path\to\repo --mode all

# machine-readable strict report
python code-cleanup-helper/scripts/audit.py C:\path\to\repo --mode all --format json --strict

# baseline／promotion evidence
python run-benchmark-driven-rd/scripts/run_cleanup_gate.py C:\path\to\repo --mode all --phase baseline
python run-benchmark-driven-rd/scripts/run_cleanup_gate.py C:\path\to\repo --mode all --phase promotion --review-policy block

# compose a mixed-project route
python run-benchmark-driven-rd/scripts/project_profile_gate.py --project C:\path\to\repo --contract C:\path\to\repo\.rd\project.json
```

Cleanup 只量測，不修改產品；R&D 才能依已授權範圍實作與 promotion。外部 create／publish／rename／archive／delete 必須先通過 canonical-target 和 postcondition gate。

## 驗證

```powershell
python code-cleanup-helper/scripts/self_test.py
python run-benchmark-driven-rd/scripts/self_test.py
python run-benchmark-driven-rd/scripts/run_cleanup_gate.py --self-test
python run-benchmark-driven-rd/scripts/regression_corpus.py
python run-benchmark-driven-rd/scripts/router_quality_corpus.py
python code-cleanup-helper/scripts/check_context_budget.py code-cleanup-helper --manifest code-cleanup-helper/profiles/context-budget.json
python code-cleanup-helper/scripts/check_context_budget.py run-benchmark-driven-rd --manifest run-benchmark-driven-rd/profiles/context-budget.json
```

做隔離的公開包驗證時，讓測試程序不繼承 `CODEX_HOME`，避免意外使用另一份本機 Cleanup provider。上述測試驗證的是 Skill／gate 行為，不代表任何下游產品已經具備 updater 或已公開發布。

## 隱私

公開包不應包含本機絕對路徑、私人 repository 內容、credential、token 或真實使用者資料。把專案專屬 privacy token／regex 寫進自己的 `audit.config.json`。

## License

[MIT](LICENSE)。Copyright holder：Hao0321 contributors。
