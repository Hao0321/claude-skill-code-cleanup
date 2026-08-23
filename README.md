# Code Cleanup + Benchmark-Driven R&D

兩個可安裝到 Codex 或 Claude Code 的工程 Skills：

- `code-cleanup-helper`：read-only repository／Skill／release evaluator。
- `run-benchmark-driven-rd`：定義可證偽目標、保存 baseline、執行實驗、控制 promotion 與外部變更。

目前版本：**v0.20.0**。

## v0.20.0 重點

- Cleanup audit 已擴充到架構依賴、必要 edge、跨語言量測缺口、能力義務、build receipt、模型／context contract、安全與 release hygiene。
- R&D 加入 capability ledger、claim matrix、delivery／web acceptance、completion closure、外部變更與 invocation revision gates。
- 新增模組化 project route：Skill、網站、資料庫、遊戲、軟體與 release／security／media／commerce overlays 可自由組合；Cleanup 保持獨立唯讀，R&D 負責決策與學習。
- 私公同步新增 managed manifest：只清理由同步器曾管理、但 canonical 私版已刪除的檔案。
- 同步寫入前先跑 privacy preflight，命中個人路徑、名稱或 secret-shaped pattern 時直接 BLOCK。

## 安裝

```bash
git clone https://github.com/Hao0321/claude-skill-code-cleanup.git
```

Codex（Windows PowerShell）：

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.codex\skills" | Out-Null
Copy-Item -Recurse ".\claude-skill-code-cleanup\code-cleanup-helper" "$env:USERPROFILE\.codex\skills\code-cleanup-helper"
Copy-Item -Recurse ".\claude-skill-code-cleanup\run-benchmark-driven-rd" "$env:USERPROFILE\.codex\skills\run-benchmark-driven-rd"
```

Claude Code：把 `.codex\skills` 改成 `.claude\skills`。macOS／Linux 可複製到 `~/.codex/skills/` 或 `~/.claude/skills/`。

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
```

## 隱私

公開包不應包含本機絕對路徑、私人 repository 內容、credential、token 或真實使用者資料。把專案專屬 privacy token／regex 寫進自己的 `audit.config.json`。

## License

[MIT](LICENSE)。Copyright holder：Hao0321 contributors。
