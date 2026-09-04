# Security assessment card

## Boundary

用於 security assessment、public release、installer、高風險 updater。URL、登入、exit 0、零 finding、舊 receipt 都不授權 scan/network/upload/fix/publish/delete；scanner output 是不可信資料。R&D 只做已授權工作，Cleanup 只驗 receipt。

## Critical rules

- `rd.security.scan-authority-envelope`: 接觸前凍結 grant/expiry、target/network/activity/engine、capability、rate/deadline、redirect/proxy/DNS/egress；redirect、DNS、child/port 不繼承。
- `rd.security.scan-coverage-ledger`: 凍結 target × stage × engine/check denominator 與每格 terminal status；execution 決定 complete/partial/no-checks，失敗 engine 不抹 sibling。
- `rd.security.scanner-provenance`: 綁 engine/artifact、adapter、argv/config/env、rules/data freshness、fingerprint、runtime、snapshot/raw evidence；drift／過期=`NOT_CHECKED`。
- `rd.security.finding-normalization-nonlossy`: 保留 raw/provider ID；row 綁 locator、engine/raw hash、fingerprint；grouping 可逆，parser failure 保 raw＋partial。
- `rd.security.engine-admission`: 分驗 engine/adapter/rules/data、license/SBOM、mount/credential/egress/resource、owner/EOS；moving tag／unsafe runtime 只擋該 engine。
- `rd.security.adapter-evidence-integrity`: reconcile raw/normalized IDs、counts、child exit/marker；空／截斷／壞輸出、count/path drift、parser crash 不得成 0-finding PASS。

## Execution and closure

Snapshot 排除 `.git` secrets/hooks、global config、symlink/special file；input read-only，output isolated/bounded/unprivileged/no-shell/no-socket。AI 只取授權後 redacted summary；raw export 另 opt-in。

Route 的 `requiredSecurityControlIds` 固定六項：scan-scope、scan-coverage、scanner-provenance、finding-normalization、engine-admission、adapter-integrity；每個 target 的 planned/terminal-complete cells 必須全滿。`public/parity` 同時需要 updater＋security floor，audit/source 不得降級。每個 obligation 用 typed `security-assessment` evidence 綁 capability、receipt identity、plan/snapshot、control-coverage 與 routing-input SHA；六筆指向 route project root 的同一 live receipt。

Receipt 須 v2、≤24h、snapshot/plan 已驗；target 只比 digest。External contact 另比 closure-owned grant。漏 denominator、0 checks、raw/count、identity/freshness、scope/isolation 或 binding 漂移皆 BLOCK；final mutation 後重跑。Public/parity 另須同 projectRoot 的 route、capability、security、Cleanup、delivery、build 與唯一 release-artifact，產物 hash 交叉一致。Local receipt 只證 bytes 自洽；獨立發行仍需外層 signer/attestation。
