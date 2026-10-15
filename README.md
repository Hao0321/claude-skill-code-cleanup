# Code Cleanup + Benchmark-Driven R&D

兩個可安裝到 Codex 或 Claude Code 的工程 Skills：

- `code-cleanup-helper`：read-only repository／Skill／release evaluator。
- `run-benchmark-driven-rd`：定義可證偽目標、保存 baseline、執行實驗、控制 promotion 與外部變更。

目前版本：**v0.22.1**。

## v0.22.1 重點

- 修正 UTF-16 macOS／Linux 私有路徑、分段 source map 與更多壓縮容器的漏判；外部 map 區段、解析邊界與未解包內容保持 `NOT_CHECKED`。
- 同步計畫鎖定完整來源選集，阻擋規劃後新增的檔案與根目錄連結；全部受管檔案的退役需要明確指定 `--allow-empty`。
- R&D 以隔離程序重播自有校準，分別記錄當前程式、fixture 與 Python 執行檔雜湊；歷史實驗維持原始內容。
- 靜態文字檢查改成有重疊的分段解碼。約 8 MiB 自有測試中，額外 Python 配置峰值降低 98.8%、中位耗時降低 45.3%；此結果不代表整套 audit 的效能，範圍見 [Changelog](CHANGELOG.md)。

## v0.22.0 重點

- Cleanup 改用可剪枝的目錄盤點，避免進入排除目錄；排除、近似名稱與中文路徑都有回歸控制。
- 公開同步採完整預檢、逐檔雜湊所有權與過期計畫檢查。私人記憶、憑證、穿越路徑、連結與被修改的受管檔案會阻擋同步；公開包自有檔案保留。
- 新增唯讀的交付物暴露檢查：內嵌私人路徑、疑似憑證、source map 原始碼、debug symbols 與 PE 宣告旗標。未解包的容器保持 `NOT_CHECKED`；它不是完整資安掃描或防逆向保證。
- 新增選用的 [REA 分析流程](run-benchmark-driven-rd/references/reverse-analysis.md)。Windows／Node 24.19.0／REA 6.5.0 已在自有 JavaScript 小範例驗證；不自動安裝 REA，原生反編譯提供者仍需另行驗證。
- 中文 machine JSON 固定 UTF-8；路由、記錄儲存、收尾驗證與測試拆分責任，保留原 CLI 入口與嚴格 `REVIEW` 規則。
- 納入按需讀取的遊戲、3D、視覺與狀態完整性經驗；單一專案的美術觀察保留 provisional 範圍，原始紀錄留在使用者自己的 `.rd/`。
- 沿用六項安全控制、同專案 delivery／build／release 綁定、安全更新／回滾與精確 context budget，不把路由或零 finding 當成產品通過。

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
python run-benchmark-driven-rd/scripts/verify_learning_bundle.py
python code-cleanup-helper/scripts/check_context_budget.py code-cleanup-helper --manifest code-cleanup-helper/profiles/context-budget.json
python code-cleanup-helper/scripts/check_context_budget.py run-benchmark-driven-rd --manifest run-benchmark-driven-rd/profiles/context-budget.json
```

做隔離的公開包驗證時，讓測試程序不繼承 `CODEX_HOME`，避免意外使用另一份本機 Cleanup provider。上述測試驗證的是 Skill／gate 行為，不代表任何下游產品已經具備 updater 或已公開發布。

## 交付物暴露與選用逆向分析

```powershell
python code-cleanup-helper/scripts/check_release_exposure.py C:\path\to\delivered-artifact
python code-cleanup-helper/scripts/benchmark_inventory.py
```

暴露檢查不執行目標、不連網、不解包。`PASS` 只涵蓋列出的靜態檢查；`REVIEW` 是待判斷候選，`NOT_CHECKED` 表示仍有缺口。重建別人的功能需要有權分析的精確目標、獨立實作和行為測試；防護應縮小交付資訊、把秘密和信任判斷放在受控伺服器。混淆、PE 旗標和反編譯難度都不能保證客戶端不可逆向。

盤點 benchmark 會建立並清理自己的暫存範例。它比較同一範例上的舊 `rglob` 與剪枝演算法，不代表整套 audit 或其他專案有相同加速比。完整紀錄方式與限制見 [Changelog](CHANGELOG.md)。

舊學習宣告與當前可重播證據分開保存，詳見 [learning history](run-benchmark-driven-rd/references/learning-history.md)。

## 隱私

公開包不應包含本機絕對路徑、私人 repository 內容、credential、token 或真實使用者資料。把專案專屬 privacy token／regex 寫進自己的 `audit.config.json`。

## License

[MIT](LICENSE)。Copyright holder：Hao0321 contributors。
