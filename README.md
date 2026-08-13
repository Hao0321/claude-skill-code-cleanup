# Code Cleanup + Benchmark-Driven R&D

一套可安裝到 Codex 或 Claude Code 的雙 Skill 工程系統：

- `code-cleanup-helper`：read-only code／skill／repository evaluator。
- `run-benchmark-driven-rd`：定義可證偽目標、保存 baseline、執行實驗、控制 promotion 與外部變更的 orchestrator。

目前穩定 release：**v0.6.0**。`main` 另包含尚未標記 release 的 Cleanup ↔ R&D machine contract：

- deterministic audit：重複段落、永久 ID、長檔、private/public sync、release、broken links、版本／事實漂移、skill metadata 與 privacy token。
- semantic scan：規則內容漂移、SoT 孤島、gate 自我認證與「文件裁決沒有機械落地」。
- benchmark gate：驗證 Cleanup JSON schema、status/count、target/mode，並凍結 evaluator/config hash。
- external-change gate：在 GitHub／雲端 create、publish、rename、archive、delete 前鎖定 canonical target、最終權限與 postconditions。

## Cleanup ↔ R&D contract

Cleanup 永遠只量測；R&D 是唯一修改與 promotion 控制面。Baseline 可以保存既有 `FAIL`，promotion 則會阻擋 `FAIL`；`REVIEW` 保持可見但不自動阻擋，required dimension 的 `NOT_CHECKED` 會阻擋 promotion。

```powershell
python run-benchmark-driven-rd/scripts/run_cleanup_gate.py C:\path\to\repo --mode architecture --phase baseline
python run-benchmark-driven-rd/scripts/run_cleanup_gate.py C:\path\to\repo --mode architecture --phase promotion --require-checked 10
```

完整契約見 [`rd-integration.md`](code-cleanup-helper/references/rd-integration.md)。

## v0.6.0 新增什麼

- Python module graph 支援直接執行 script 的 bare sibling imports，同時保留真正 top-level 與標準庫 imports。
- `required_dependencies` 可把「架構理應存在的邊」寫成 gate；缺邊是 FAIL，不再把稀疏空圖誤報成乾淨。
- 新增 sibling positive、missing-edge、root-module 與 stdlib negative fixtures。
- Self-test 依責任拆分，完整涵蓋 dependency、cycle、layer、duplicate、function-size 與 JSON contract。
- 新增 config-driven public sync，且通用 skill 不再預設載入作者私人 voice。

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
cd code-cleanup-helper
$env:PYTHONUTF8='1'

# deterministic A+B audit
python scripts/audit.py C:\path\to\repo --mode all

# machine-readable report
python scripts/audit.py C:\path\to\repo --mode all --format json

# semantic deep scan
python cleanup_scan.py C:\path\to\repo
```

CI 要在有 FAIL 時回傳非零 exit code，才加 `--strict`：

```powershell
python scripts/audit.py C:\path\to\repo --mode all --strict
```

## 兩個引擎怎麼選

| 問題 | 工具 |
|---|---|
| Broken link、版本宣告、ID range、sync、隱私 token | `scripts/audit.py` |
| Exact paragraph duplication、長檔、skill metadata | `scripts/audit.py` |
| 同一規則 ID 在不同文件講不同話 | `cleanup_scan.py` |
| 姊妹模組互不引用、gate 只有自建 fixture | `cleanup_scan.py` |
| Release 前完整健檢 | 兩個都跑 |
| 定義 baseline、promotion、實驗與可重用決策 | `run-benchmark-driven-rd` |
| GitHub／雲端發布、刪除或權限變更前的 canonical-target gate | `run-benchmark-driven-rd` |

## 設定

把 [`audit.config.example.json`](code-cleanup-helper/audit.config.example.json) 複製到目標 repo 根目錄並命名為 `audit.config.json`。完整 schema 見 [`config-and-report.md`](code-cleanup-helper/references/config-and-report.md)。

未設定 `sync.public_root` 時，sync 結果是 `NOT_CHECKED`，不是 PASS。外部 URL 預設不打網路，也不會假裝已驗證。

## 安全邊界

Cleanup 引擎永遠只讀。單獨 audit 時先報告再等修復授權；若原始請求已明確要求 R&D 實作，Cleanup 只把證據交回 orchestrator，不重複索取授權。外部 create／publish／delete 仍必須通過 canonical-target、技術權限與 postcondition gate。

## 驗證

```powershell
python code-cleanup-helper/scripts/self_test.py
python code-cleanup-helper/cleanup_scan.py --selftest
python run-benchmark-driven-rd/scripts/self_test.py
python run-benchmark-driven-rd/scripts/run_cleanup_gate.py --self-test
python run-benchmark-driven-rd/scripts/regression_corpus.py
```

## License

[MIT](LICENSE)。作者：駱君昊（Hao）。姐妹專案：[social-post](https://github.com/Hao0321/claude-skill-social-post)。
