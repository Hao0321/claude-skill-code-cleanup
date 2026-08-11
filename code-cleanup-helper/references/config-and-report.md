# Audit config 與 report schema

在目標根目錄建立 `audit.config.json`。不用 YAML，避免 PyYAML 依賴與 Windows 環境差異。

```json
{
  "exclude": [".git/**", "node_modules/**", "private/**"],
  "length_exceptions": ["references/generated-index.md"],
  "navigation_exceptions": ["references/cases/case-*.md"],
  "id_definition_scopes": {
    "R": ["references/rules/R*.md"],
    "F": ["references/formulas.md"],
    "CASE": ["references/cases/case-*.md"]
  },
  "range_claim_scopes": {
    "R": ["references/rules.md"],
    "F": ["references/formulas-index.md"],
    "CASE": ["references/case_studies.md"]
  },
  "thresholds": {
    "skill_warning": 200,
    "skill_severe": 400,
    "reference_warning": 400,
    "reference_severe": 800,
    "code_warning": 500,
    "code_severe": 1000
  },
  "sync": {
    "public_root": null,
    "normalize_text": true,
    "ignore": ["style_profile.md", "content_plan.md", "data/**"]
  },
  "drift_assertions": [
    {
      "id": "forbid-old-sample-count",
      "files": ["SKILL.md"],
      "pattern": "AI 短劇.*n=1",
      "expected_count": 0,
      "message": "AI 短劇速查仍保留舊 n=1"
    }
  ],
  "privacy": {
    "tokens": ["C:/Users/作者名", "私人品牌詞"],
    "patterns": ["C:[/\\\\]Users[/\\\\][^/\\\\]+"],
    "allow": ["private/**"]
  }
}
```

`privacy.tokens` 是 literal 字串；Windows 反斜線不會被當 regex escape。需要正則時使用 `privacy.patterns`；無效 regex 會回報 FAIL，不會讓 audit crash。

`drift_assertions` 的 `pattern` 是 Python regex；`files` 使用 glob；`expected_count` 預設 0。把穩定、可機械驗證的事實放這裡，不把分析推論硬寫成 assertion。

`sync.normalize_text` 預設為 `true`，因此 LF／CRLF 與 UTF-8 BOM 差異不會製造假 desync；若需要 byte-for-byte 發布驗證才設為 `false`。

JSON report 欄位：

- `schema_version`：報告格式版本。
- `target／mode／config`：執行範圍。
- `summary`：files、lines、bytes、PASS、FAIL、NOT_CHECKED。
- `inventory`：每檔行數、bytes、SHA-256。
- `findings`：dimension、status、code、message、path、line、details。

`details` 是機器可讀證據；人類報告只顯示前 N 筆，避免把 terminal 塞滿。
