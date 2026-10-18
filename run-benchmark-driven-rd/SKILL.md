---
name: run-benchmark-driven-rd
description: 可否證、benchmark-gated R&D；可分發專案／Skill 預設涵蓋 GitHub 安全更新、回滾、舊版淘汰。
---

# Run Benchmark-Driven R&D

## Contract

1. Active private Skill 唯一權威。先 `invocation_revision_gate.py capture` 凍結雙 revision，決策前 `verify`；`UNSTABLE` 不混用，`STALE` 重讀重驗。
2. 修改不越原始授權；本機實作不暗含外部／破壞性 mutation。外部變更須當輪授權、精確 target、preflight、post-readback；GitHub URL 不授權執行。
3. 先定 claim、baseline、threshold、decision rule，以 task-shaped 正負控制校準 evaluator。工具綠燈不等於品質、完成或 parity；缺同 provenance 證據保持 `unmeasured`／`NOT_CHECKED`。
4. Cleanup 是獨立唯讀 provider；保留 PASS／FAIL／REVIEW／NOT_CHECKED、child、revision evidence；strict promotion 不可改寫缺口為 PASS。
5. Route receipt 列 intent、stage、artifact/risk、selected/omitted topics、hash、critical IDs、cost、fallback；未知／歧義／stale／超 budget 時 block 或 legacy fallback。
6. Private learning 存目標 `.rd/`，不預載；shared rule 需 typed receipt、單一 owner、privacy、正負 fixture、reciprocal link。縮短 context 不刪記憶。
7. 可分發目標的已授權 implementation／promotion／completion 預設需安全更新能力；audit／security-assessment／source-only 不推導 updater、publish、sign、persistence、delete 權限。
8. Security route 每個 target 必須規劃並驗完固定六控制；public／parity 再綁同專案 Cleanup、delivery、build 與 release artifact，sibling decoy 無效。
9. 收尾、重試或交接依 `references/disk-hygiene.md` 清理授權內可重建舊產物。

## 路由

| 任務 | 讀取 |
|---|---|
| Experiment | `references/topics/core-experiment.md` |
| 架構／Cleanup baseline | `references/topics/architecture-and-evaluator.md` |
| 逆向分析／交付物暴露 | `references/topics/reverse-engineering.md` |
| PR 採用 | `references/topics/community-pr-adoption.md` |
| 外部 Skill／plugin | `references/topics/agent-workflow-adoption.md` |
| context／Token／learning | `references/topics/context-and-learning.md` |
| 交易／帳號／備份／持久化 | `references/topics/state-integrity.md` |
| 3D 角色／UV／Unreal | `references/topics/character-3d-workflow.md` |
| 視覺／UI／材質 | `references/topics/visual-quality.md` |
| capability／complete／external | `references/topics/completion-and-external.md` |
| updater／可分發交付 | `references/topics/secure-self-update.md`；依風險加 delivery/security，audit／source-only 除外 |

大 contract 僅 legacy fallback；維護：`references/maintenance.md`。

## 工作流

1. 解析絕對 repo、授權、contract、obligations、failures、`.rd/`；route 含 typed `updateObligation`／capability floor。
2. 以 Cleanup＋native gate 凍結 baseline 與 claim matrix／provenance。
3. 做最小決定性實驗，保存 executable、stdout/stderr、exit、elapsed、input/environment hash、artifact、failure type。
4. 原子寫 typed record 到 `.rd/`；promotion gate 後才更新 shared topic/index。
5. 重跑相同 benchmark、負控制、delivered journey、obligations；最後修改後重驗 freshness/revision。
6. 分開報告 measured stronger／likely but unmeasured／unchanged／regressed/open；PASS 數不等於整體變強。

```powershell
python scripts/project_profile_gate.py --project <target> --contract <task-contract.json> --output <route.json> --quiet
```

Skill 下次 invocation／restart 切換；背景、自啟、破壞性 migration 分開 opt-in。
