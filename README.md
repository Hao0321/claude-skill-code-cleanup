# code-cleanup-helper

一個可安裝到 Codex 或 Claude Code 的 read-only code／skill／repository audit skill。

目前版本：**v0.6.0**。它把兩種互補能力放在同一套工作流：

- deterministic audit：重複段落、永久 ID、長檔、private/public sync、release、broken links、版本／事實漂移、skill metadata 與 privacy token。
- semantic scan：規則內容漂移、SoT 孤島、gate 自我認證與「文件裁決沒有機械落地」。

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

## 設定

把 [`audit.config.example.json`](code-cleanup-helper/audit.config.example.json) 複製到目標 repo 根目錄並命名為 `audit.config.json`。完整 schema 見 [`config-and-report.md`](code-cleanup-helper/references/config-and-report.md)。

未設定 `sync.public_root` 時，sync 結果是 `NOT_CHECKED`，不是 PASS。外部 URL 預設不打網路，也不會假裝已驗證。

## 安全邊界

Audit 本身只讀。skill 會先報告，再等你確認修改範圍；不會自動刪檔、改 `.git/`、改 CI／license、commit、push 或發布 release。

## 驗證

```powershell
python code-cleanup-helper/scripts/self_test.py
python code-cleanup-helper/cleanup_scan.py --selftest
```

## License

[MIT](LICENSE)。作者：駱君昊（Hao）。姐妹專案：[social-post](https://github.com/Hao0321/claude-skill-social-post)。
