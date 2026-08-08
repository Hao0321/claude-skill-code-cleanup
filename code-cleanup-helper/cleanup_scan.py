# -*- coding: utf-8 -*-
"""cleanup_scan.py — code-cleanup-helper 的可執行掃描器（v0.4，2026-08-07 建）

**為什麼 v0.4 要有這支檔**：v0.1-v0.3 的 SKILL.md 是一份「給人抄的 bash checklist」。
問題有三：
  1. 全是 bash —— 作者本人是 Windows 用戶，貼上去跑不動
  2. 沒有任何自我檢查 —— 一支叫別人查技術債的 skill，自己零測試
  3. 只查得到**檔案層**（重複/命名/長度/版本號/link），查不到**語意層**
     （規則內容漂移、引用已作廢定義、該連的沒連、gate 自我認證）

本檔把「機械查得出來的」全部變成可執行，判斷題留在 SKILL.md 給人跑。

維度覆蓋（S=可機械掃 / H=需人判斷，留在 SKILL.md）：
    D1  重複內容 DRY            S   跨檔重複行
    D2  命名不一致               S   競爭中的 ID 體系
    D3  可抽模組                 H
    D4  過長檔案                 S   行數 vs 型別門檻
    D5  私公版 sync              H   （需兩個 repo 路徑）
    D6  release 一致性           H   （需 git/gh）
    D7  cross-link 完整性        S   markdown link 解析
    D8  版本標記漂移             S   逐檔 version 對全域最大值
    D9  開源交接健檢             H
    D10 **規則內容漂移**         S   ⭐ v0.4 新增：同一規則 ID 在不同檔案講不同話
    D11 **孤島 / SoT 缺失**      S   ⭐ v0.4 新增：互相該連卻零引用的姊妹檔
    D12 **gate 自我認證**        S   ⭐ v0.4 新增：只有 self-test、沒有真 corpus 回歸（M114）
    D13 **裁決無機械落地**       S   ⭐ v0.4 新增：ledger 有規則但沒 gate 撐

severity：CRITICAL > HIGH > MED > LOW。報告依 severity 排序，不是依維度編號 ——
「先修哪個」比「有幾類問題」重要。

用法：
    python cleanup_scan.py <root> [--json out.json] [--max-files 400]
    python cleanup_scan.py --selftest

cp950 安全：print 只 ASCII；檔案 I/O 一律 encoding="utf-8"。
"""

from __future__ import annotations

import io
import json
import os
import re
import sys
from collections import Counter, defaultdict

# ═══════════════════════════════════════════════ 設定

TEXT_EXT = {".md", ".py", ".ts", ".tsx", ".js", ".json", ".yml", ".yaml", ".txt"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv",
             "dist", "build", "_demo", "_archive", ".pytest_cache"}

# D4 長度門檻 (warn, fail)。
# ⚠️ 來源：v0.1 沿用至今的經驗值，**未經校準**。
#    真要嚴謹該照 M114 拿真 repo 分佈回歸（見 SKILL.md「門檻誠實聲明」）。
LENGTH_LIMITS = [
    (re.compile(r"SKILL\.md$", re.I),        200, 400),
    (re.compile(r"CHANGELOG\.md$", re.I),    400, 1200),
    (re.compile(r"\.md$", re.I),             400, 800),
    (re.compile(r"\.(py|ts|tsx|js)$", re.I), 500, 1000),
]

DUP_MIN_LEN = 30          # 重複行最短長度
DUP_MIN_FILES = 3         # 出現在幾個不同檔案才算 DRY 違反
LONG_FUNC_WARN = 50
LONG_FUNC_FAIL = 100

# D2 競爭中的 ID 體系（同一組概念的多種寫法 → 只該留一種）
# 第三欄 = 適用副檔名。🐛 dogfood 抓到：不分檔型的話，掃描器會把自己原始碼裡的
# **正則字面值**（`r"\bR\d{1,2}[:：]"`）當成「有人在用 R5 這種寫法」。
# 規則編號 / 維度編號是**文件層**概念；命名風格是**程式層**概念，各掃各的。
NAMING_RIVALS = [
    ("rule-id", [re.compile(r"\bR\d{1,2}[:：]"), re.compile(r"規則\s*\d{1,2}"),
                 re.compile(r"\bRule\s*\d{1,2}")], {".md"}),
    ("dimension", [re.compile(r"\bDimension\s*\d"), re.compile(r"維度\s*\d")], {".md"}),
    ("case", [re.compile(r"\bsnake_case\b"), re.compile(r"\bcamelCase\b")],
     {".py", ".ts", ".tsx", ".js"}),
]

# D10 規則 ID 樣式（抓「同一個 ID 在不同檔案講不同話」）
RULE_ID_RE = re.compile(r"\b(M\d{1,3}|R\d{1,2}|[SDGVP]-[A-Z]\b)")
DRIFT_MIN_OVERLAP = 0.30  # 描述 token 重疊率低於此 = 疑似漂移

# D12 gate 檔命名 + 回歸夥伴命名
GATE_FILE_RE = re.compile(r"(gate|check|validat|lint)\w*\.py$", re.I)
CORPUS_HINT_RE = re.compile(r"corpus|calibrat|regression|golden|fixture_real|真樣本|回歸", re.I)

VERSION_RE = re.compile(r"\bv?(\d+)\.(\d+)(?:\.(\d+))?\b")
# 版本**宣告**行（不是散文提及）—— 詳見 _versions() 的三連踩註解
_VERSION_DECL_RE = re.compile(
    r"^\s*(?:#{1,6}\s*|[-*]\s+|##?\s*)?v\d+\.\d+"
    r"|^\s*[\"']?(?:version|__version__)[\"']?\s*[:=]\s*[\"']?v?\d+\.\d+",
    re.I)
MD_LINK_RE = re.compile(r"\[([^\]]{1,80})\]\(([^)\s]+)\)")

SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MED": 2, "LOW": 3}


# ═══════════════════════════════════════════════ 掃檔

def _read(path):
    try:
        with io.open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except (OSError, UnicodeError):
        return ""


def collect(root, max_files=400):
    """回傳 [{path, rel, lines, text}]，跳過 SKIP_DIRS 與非文字副檔名。"""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if os.path.splitext(fn)[1].lower() not in TEXT_EXT:
                continue
            p = os.path.join(dirpath, fn)
            text = _read(p)
            if not text:
                continue
            out.append({
                "path": p,
                "rel": os.path.relpath(p, root).replace("\\", "/"),
                "lines": text.count("\n") + 1,
                "text": text,
            })
            if len(out) >= max_files:
                return out
    return out


def _finding(dim, severity, title, detail, where=""):
    return {"dim": dim, "severity": severity, "title": title,
            "detail": detail, "where": where}


# ═══════════════════════════════════════════════ D1 重複

def d1_duplication(files):
    seen = defaultdict(set)
    for f in files:
        for raw in f["text"].split("\n"):
            s = raw.strip()
            if len(s) < DUP_MIN_LEN or s.startswith(("#", "//", "|---", "```")):
                continue
            seen[s].add(f["rel"])
    out = []
    for line, where in seen.items():
        if len(where) < DUP_MIN_FILES:
            continue
        # 全部落在同一個父目錄 = 樣板家族（generated examples / persona 模板），
        # 重複是**設計如此**，不是技術債 → 降級，避免報告被樣板洗版。
        # （dogfood 發現：huashu-nuwa/examples/ 下 14 個 persona skill 由同一模板生成）
        parents = {w.rsplit("/", 2)[0] if w.count("/") >= 2 else w.split("/")[0]
                   for w in where}
        template_family = len(parents) == 1
        if template_family:
            sev = "LOW"
        else:
            sev = "HIGH" if len(where) >= 5 else "MED"
        out.append(_finding(
            "D1", sev, "跨 %d 檔重複同一行%s"
            % (len(where), "（同一樣板家族，可能是設計如此）" if template_family else ""),
            line[:90] + ("..." if len(line) > 90 else ""),
            ", ".join(sorted(where)[:5])))
    out.sort(key=lambda x: -len(x["where"]))
    return out[:20]


# ═══════════════════════════════════════════════ D2 命名

def d2_naming(files):
    out = []
    for label, rivals, exts in NAMING_RIVALS:
        hits = Counter()
        where = defaultdict(set)
        for f in files:
            if os.path.splitext(f["rel"])[1].lower() not in exts:
                continue
            for i, rx in enumerate(rivals):
                n = len(rx.findall(f["text"]))
                if n:
                    hits[i] += n
                    where[i].add(f["rel"])
        # 現實症狀通常是「主流用法 50 次 + 殘留舊寫法 1 次」，
        # 所以單次殘留也要算進來（只要總量足夠、確實有兩套並存）。
        used = [i for i in hits if hits[i] >= 1]
        if len(used) >= 2 and sum(hits[i] for i in used) >= 3:
            desc = " vs ".join("%s(%d次)" % (rivals[i].pattern, hits[i]) for i in used)
            out.append(_finding(
                "D2", "MED", "「%s」有 %d 套並存的命名體系" % (label, len(used)),
                desc + " -> 選一個 canonical，其餘 rename",
                ", ".join(sorted(set().union(*[where[i] for i in used]))[:5])))
    return out


# ═══════════════════════════════════════════════ D4 長度

def _limits_for(rel):
    for rx, warn, fail in LENGTH_LIMITS:
        if rx.search(rel):
            return warn, fail
    return None


def d4_length(files):
    out = []
    for f in files:
        lim = _limits_for(f["rel"])
        if not lim:
            continue
        warn, fail = lim
        if f["lines"] > fail:
            out.append(_finding("D4", "HIGH", "檔案過長 %d 行" % f["lines"],
                                "超過嚴重線 %d -> 建議拆檔" % fail, f["rel"]))
        elif f["lines"] > warn:
            out.append(_finding("D4", "MED", "檔案偏長 %d 行" % f["lines"],
                                "超過警告線 %d" % warn, f["rel"]))
    # 長函數（Python）
    for f in files:
        if not f["rel"].endswith(".py"):
            continue
        cur, start, name = 0, 0, None
        for i, line in enumerate(f["text"].split("\n"), 1):
            m = re.match(r"^(\s*)def\s+(\w+)", line)
            if m and len(m.group(1)) <= 4:
                if name and cur > LONG_FUNC_WARN:
                    sev = "HIGH" if cur > LONG_FUNC_FAIL else "MED"
                    out.append(_finding("D4", sev, "函數過長 %d 行" % cur,
                                        "def %s (L%d)" % (name, start), f["rel"]))
                name, start, cur = m.group(2), i, 0
            elif name:
                cur += 1
        if name and cur > LONG_FUNC_WARN:
            sev = "HIGH" if cur > LONG_FUNC_FAIL else "MED"
            out.append(_finding("D4", sev, "函數過長 %d 行" % cur,
                                "def %s (L%d)" % (name, start), f["rel"]))
    return out


# ═══════════════════════════════════════════════ D7 broken link

def d7_links(files, root):
    """只掃 .md。

    🐛 **dogfood 抓到**：初版掃所有文字檔 → 把 `.py` 原始碼裡的字串
       （包含本檔 self-test fixture 的 `[壞掉](./nope.md)`）當成真的 markdown 連結。
       程式碼裡的括號語法不是連結。
    """
    out = []
    for f in files:
        if not f["rel"].lower().endswith(".md"):
            continue
        base = os.path.dirname(f["path"])
        for text, target in MD_LINK_RE.findall(f["text"]):
            if re.match(r"^(https?:|mailto:|#)", target):
                continue
            clean = target.split("#")[0].strip()
            if not clean:
                continue
            # 🐛 v0.4.1（外部 review 抓到）：`[hi](摳luma>200亮部)` 這種**中文偽連結記法**
            # 被當成 CRITICAL 斷鏈。target 要長得像路徑（含斜線或副檔名）才進判定；
            # 純散文 target 跳過 —— 寧可少抓，不要把筆記記法當成壞連結。
            if not re.search(r"[\\/]|\.[A-Za-z0-9]{1,5}$", clean):
                continue
            cand = clean if os.path.isabs(clean) else os.path.join(base, clean)
            if not os.path.exists(cand) and not os.path.exists(os.path.join(root, clean)):
                out.append(_finding("D7", "CRITICAL", "連結指向不存在的檔案",
                                    "[%s](%s)" % (text[:40], target), f["rel"]))
    return out[:30]


# ═══════════════════════════════════════════════ D8 版本漂移

def _versions(text):
    """抽版本號 —— 只認**宣告**，不認散文裡的提及。

    🐛 **dogfood 三連踩**（同一類錯誤：掃描器讀到自己的範例）：
       ① 初版對全文跑 `\\d+\\.\\d+` → 把 `THRESHOLD = 0.30`、`1.0` 當版本
       ② 改成「有 v 前綴或該行含 version 關鍵字」→ 仍把自己 self-test 裡的
          `_versions("v0.7.3")` 斷言字串當成宣告
       ③ 甚至把自己 docstring 裡描述 bug 用的假版本號當成真版本
    → 定版：**只有宣告語法算數**
         `## v1.2.3`（標題）／`- v1.2`（清單）／`version: 1.2.3`／`__version__ = "1.2.3"`
       散文中段的 `v0.4`、字串字面值、數值常數**一律不算**。
       寧可少抓（D8 漏報）也不要無中生有（憑空造出不存在的版本 = 報告不可信）。
    """
    out = set()
    for line in text.split("\n"):
        if not _VERSION_DECL_RE.match(line):
            continue
        for m in VERSION_RE.finditer(line):
            a, b, c = m.groups()
            out.add((int(a), int(b), int(c or 0)))
    return out


def d8_version_drift(files):
    per = {}
    for f in files:
        vs = _versions(f["text"])
        if vs:
            per[f["rel"]] = max(vs)
    if len(per) < 2:
        return []
    newest = max(per.values())
    out = []
    for rel, v in sorted(per.items()):
        if v < newest and (newest[0], newest[1]) != (v[0], v[1]):
            out.append(_finding(
                "D8", "HIGH", "版本標記落後",
                "此檔最新提到 v%d.%d.%d，全庫最新 v%d.%d.%d" % (v + newest), rel))
    return out


# ═══════════════════════════════════════════════ D10 規則內容漂移 ⭐

# 「這一行**定義**規則」而不是「談論規則」的判別。
#
# 🐛 **dogfood 第二輪抓到**：初版用關鍵詞（必須/所有/降級…）判斷 → 抓到的是**語氣**不是語法。
#    「① R21 降級同步到其他 skill」（待辦）與「R21 被寫進多個 skill」（提醒註記）
#    都是**在談論**這條規則，卻被當成規則定義互相對撞。
# → 改用**位置＋語法**：規則定義行一定是「ID 在行首 + 緊跟定義符號」：
#      R5：...        ### R2：...        | **R1** | ...        - **R3**: ...
#    談論它的行，ID 必然出現在句中 → 直接排除。
_RULE_DEF_RE = re.compile(
    r"^[\s>#*|\-•\d.)]{0,8}\**\s*(M\d{1,3}|R\d{1,2}|[SDGVP]-[A-Z])\**\s*[:：|、]")

# 會議記錄 / 稽核日誌 / 版本史 —— 本來就不是規則的來源，不參與 D10 比對。
# ⚠️ 刻意**不含** `notes` —— 初版含了，結果連自己的測試 fixture `notes.md` 都排除掉；
#    真實專案的 notes.md 很可能就是規則所在地，排除太粗暴。真正的問題檔是 `*-log.md`。
_LOG_FILE_RE = re.compile(r"(log|audit|changelog|history|journal)\b", re.I)

# changelog / 版本紀錄 / 輪次標籤 —— 不是規則陳述。
# 🐛 dogfood 抓到：「| 0.3.2 | 2026-08-07 | **R3 訪談落地** ...」被當成 R3 這條規則的定義，
#    但 R1-R5 在那裡是**訪談輪次編號**，跟規則 R3 完全無關。
_CHANGELOG_LINE_RE = re.compile(
    r"\bv?\d+\.\d+\.\d+\b|\b20\d\d-\d\d-\d\d\b|訪談落地|Changelog|改版紀錄", re.I)


def _tokens(s):
    """中英混合斷詞。

    🐛 **v0.4 開發時抓到的 bug**：初版只用 `[一-鿿A-Za-z0-9]{2,}`，
       中文沒有空格 → 整串中文被當成**一個 token**。
       「所有的決定都必須先經過圓桌」vs「只有策略級才需要開圓桌」
       算出來相似度 50%（因為共用 "R5" 這個 token）→ 完全漏抓。
    → 中文改用**字元 bigram**（標準中文相似度做法），英數維持 word-level。
    """
    out = set(re.findall(r"[A-Za-z0-9]{2,}", s.lower()))
    for run in re.findall(r"[一-鿿]+", s):
        if len(run) == 1:
            out.add(run)
        for i in range(len(run) - 1):
            out.add(run[i:i + 2])
    return out


def _namespace(rel):
    """規則 ID 的命名空間 = 頂層模組資料夾。

    🐛 **dogfood 抓到的致命誤報**：初版跨全庫比對同名規則 ID →
       A skill 的 R1（絕不刪東西）被拿去跟 B skill 的 R1
       （不可逆決策不硬套公式）比 → 判定「規則漂移」。
       但那是**兩條完全不同的規則剛好共用區域編號**，不是漂移。
    → 規則 ID 是**每個 skill 各自的命名空間**，只在同命名空間內比。
    """
    parts = rel.split("/")
    return parts[0] if len(parts) > 1 else "(root)"


def d10_rule_drift(files):
    """同一命名空間內，同一個規則 ID 被描述成不同意思 = 規則漂移。

    真實案例（2026-08-07）：作者把 R21 從「所有決定都要開圓桌」降級為
    「只有策略級才開」，但下游三個 skill 仍寫舊版 —— 版本號完全沒變，
    D8 抓不到，只有比對**規則內容**才看得出來。
    """
    # ns -> rule_id -> [(rel, 該行文字)]
    desc = defaultdict(lambda: defaultdict(list))
    for f in files:
        if _LOG_FILE_RE.search(os.path.basename(f["rel"])):   # 記錄檔不是規則來源
            continue
        # 🐛 v0.4.1（外部 review 抓到）：**定義只住在 .md**。程式碼註解裡的
        # `# M115: current.mp4 是單一目前成片` 是**引用**不是競爭定義——引用天生
        # 比定義短，重疊率必低，把它們對比等於保證誤報（實測一個 repo 炸出 11 個
        # 假 CRITICAL）。.py/.ts 引用歸 D13 家族的「有沒有落地」問題，不歸漂移。
        if not f["rel"].lower().endswith(".md"):
            continue
        ns = _namespace(f["rel"])
        for line in f["text"].split("\n"):
            s = line.strip()
            if len(s) < 15 or len(s) > 400:
                continue
            if _CHANGELOG_LINE_RE.search(s):   # 版本紀錄/輪次標籤，不是規則陳述
                continue
            m = _RULE_DEF_RE.match(s)          # 必須是「定義行」，不是「談論行」
            if not m:
                continue
            if len(set(RULE_ID_RE.findall(s))) != 1:   # 一行多個 ID = 索引/對照表
                continue
            desc[ns][m.group(1)].append((f["rel"], s))

    out = []
    for ns in sorted(desc):
        for rid, items in sorted(desc[ns].items()):
            by_file = defaultdict(list)
            for rel, s in items:
                by_file[rel].append(s)
            if len(by_file) < 2:
                continue
            reps = {rel: max(v, key=len) for rel, v in by_file.items()}
            rels = sorted(reps)
            base_rel = rels[0]
            base = _tokens(reps[base_rel])
            for rel in rels[1:]:
                other = _tokens(reps[rel])
                if not base or not other:
                    continue
                overlap = len(base & other) / float(min(len(base), len(other)))
                if overlap < DRIFT_MIN_OVERLAP:
                    out.append(_finding(
                        "D10", "CRITICAL",
                        "規則 %s 在 `%s` 內講不同話" % (rid, ns),
                        "重疊率僅 %.0f%% | %s: %s || %s: %s"
                        % (overlap * 100, base_rel, reps[base_rel][:60],
                           rel, reps[rel][:60]),
                        "%s <-> %s" % (base_rel, rel)))
    return out[:15]


# ═══════════════════════════════════════════════ D11 孤島 / SoT ⭐

def d11_islands(files, root):
    """互相該連卻零引用的姊妹檔。

    真實案例（2026-08-07）：作者的 voice 檔（他是誰/怎麼取捨）與 style 檔
    （他怎麼講話）是同一件事的兩半，grep 互相提及 **0 次** ——
    「分身」實際上是兩個半身。link 沒壞（D7 過），但**該連的沒連**。
    """
    skills = defaultdict(list)
    for f in files:
        parts = f["rel"].split("/")
        if len(parts) >= 2:
            skills[parts[0]].append(f)
    if len(skills) < 2:
        return []

    names = sorted(skills)
    mentions = {}
    for a in names:
        blob = "\n".join(f["text"] for f in skills[a])
        mentions[a] = {b for b in names if b != a and b in blob}

    out = []
    for a in names:
        if not mentions[a] and len(skills[a]) >= 2:
            out.append(_finding(
                "D11", "MED", "孤島：`%s` 完全不提任何姊妹模組" % a,
                "%d 個檔案、0 次 cross-reference。確認是刻意獨立，還是該連沒連"
                % len(skills[a]), a))
    return out


# ═══════════════════════════════════════════════ D12 gate 自我認證 ⭐

def d12_gate_selfcert(files):
    """M114：只有 self-test、沒有真 corpus 回歸的 gate = 被稽核方自己蓋章。

    真實案例（2026-08-07）：voice_gate self-test 35/35 全綠，
    拿 36 篇真腳本一掃 → Low/Vlog **5/5 全部誤報**。
    fixture 是照著規則寫的，規則錯在哪，fixture 就一起錯在哪。
    """
    gates = [f for f in files if GATE_FILE_RE.search(os.path.basename(f["rel"]))]
    if not gates:
        return []
    corpus_files = [f for f in files
                    if CORPUS_HINT_RE.search(os.path.basename(f["rel"]))]
    out = []
    for g in gates:
        has_selftest = "selftest" in g["text"] or "self_test" in g["text"]
        # 同目錄有回歸夥伴？或本檔自己就引用真實資料路徑？
        gdir = os.path.dirname(g["rel"])
        partner = any(os.path.dirname(c["rel"]) == gdir for c in corpus_files)
        refs_real = bool(CORPUS_HINT_RE.search(g["text"]))
        if has_selftest and not (partner or refs_real):
            out.append(_finding(
                "D12", "HIGH", "gate 只有 self-test，缺真 corpus 回歸",
                "M114：fixture 照規則寫，規則錯 fixture 一起錯。"
                "需要正向（真實產出不得誤殺）+ 反向（明顯壞東西必須抓到）對照",
                g["rel"]))
        elif not has_selftest:
            out.append(_finding(
                "D12", "MED", "gate 沒有 self-test",
                "至少要能一鍵驗證規則本身沒寫壞", g["rel"]))
    return out


# ═══════════════════════════════════════════════ D13 裁決無機械落地 ⭐

LEDGER_HINT_RE = re.compile(r"裁決|ledger|ruling", re.I)
UNLANDED_RE = re.compile(r"[⬜□]|待建|尚未|TODO|未落地")


def d13_unlanded_rules(files):
    """ledger 類檔案裡「只寫在文件、沒有機械落地」的裁決。

    原則來自 Hao 自己的裁決台帳檔頭：「只寫在文件裡＝會忘」。
    """
    out = []
    for f in files:
        if not LEDGER_HINT_RE.search(f["rel"]) and not LEDGER_HINT_RE.search(
                f["text"][:400]):
            continue
        rows = [l for l in f["text"].split("\n")
                if l.strip().startswith("|") and UNLANDED_RE.search(l)]
        if rows:
            out.append(_finding(
                "D13", "MED", "台帳有 %d 條裁決沒有機械落地" % len(rows),
                "只寫在文件裡＝會忘。判斷題可以留白，但要標明「本質不可機械化」"
                "而不是空著", f["rel"]))
    return out


# ═══════════════════════════════════════════════ 主流程

DIMS = [
    ("D1", d1_duplication, False),
    ("D2", d2_naming, False),
    ("D4", d4_length, False),
    ("D7", d7_links, True),
    ("D8", d8_version_drift, False),
    ("D10", d10_rule_drift, False),
    ("D11", d11_islands, True),
    ("D12", d12_gate_selfcert, False),
    ("D13", d13_unlanded_rules, False),
]


def scan(root, max_files=400):
    files = collect(root, max_files)
    findings = []
    for _dim, fn, needs_root in DIMS:
        findings.extend(fn(files, root) if needs_root else fn(files))
    findings.sort(key=lambda x: (SEVERITY_ORDER[x["severity"]], x["dim"]))
    counts = Counter(f["severity"] for f in findings)
    return {
        "root": root,
        "files": len(files),
        "lines": sum(f["lines"] for f in files),
        "counts": dict(counts),
        "findings": findings,
    }


def format_report(rep, limit=25):
    L = []
    L.append("CLEANUP SCAN REPORT")
    L.append("=" * 62)
    L.append("root:  %s" % rep["root"])
    L.append("scope: %d files / %d lines" % (rep["files"], rep["lines"]))
    c = rep["counts"]
    L.append("found: CRITICAL=%d HIGH=%d MED=%d LOW=%d"
             % (c.get("CRITICAL", 0), c.get("HIGH", 0),
                c.get("MED", 0), c.get("LOW", 0)))
    L.append("-" * 62)
    if not rep["findings"]:
        L.append("clean - no mechanical findings")
    for i, f in enumerate(rep["findings"][:limit], 1):
        L.append("%2d. [%-8s %s] %s" % (i, f["severity"], f["dim"], f["title"]))
        if f["where"]:
            L.append("      where: %s" % f["where"])
        L.append("      %s" % f["detail"])
    if len(rep["findings"]) > limit:
        L.append("... and %d more (use --json for full list)"
                 % (len(rep["findings"]) - limit))
    L.append("-" * 62)
    L.append("NOTE: 機械掃只覆蓋 D1/D2/D4/D7/D8/D10/D11/D12/D13。")
    L.append("      D3 模組化 / D5 私公版 / D6 release / D9 交接健檢 = 判斷題，")
    L.append("      照 SKILL.md 人工跑。**掃描綠 != 專案健康**。")
    return "\n".join(L)


# ═══════════════════════════════════════════════ self-test
# 吃自己的狗糧：本檔自己就是「叫別人測試的工具要先測自己」的示範（M114）。

def _selftest():
    import shutil
    import tempfile

    failed = []

    def check(name, cond):
        print("[%s] %s" % ("PASS" if cond else "FAIL", name))
        if not cond:
            failed.append(name)

    tmp = tempfile.mkdtemp(prefix="cleanupscan_")
    try:
        def w(rel, text):
            p = os.path.join(tmp, rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with io.open(p, "w", encoding="utf-8") as f:
                f.write(text)
            return p

        dup = "這一整行內容夠長而且會在好幾個檔案裡面重複出現造成 DRY 違反"
        w("alpha/SKILL.md",
          "# alpha\n%s\nR5：所有的決定都必須先經過圓桌會議才可以執行下去\n"
          "見 [壞掉](./nope.md)\n還有 [hi](摳luma>200亮部) 這種筆記記法\nv0.9.0\n" % dup)
        w("alpha/notes.md", "%s\n規則 5 講的是另一件事\nR5：只有策略級才需要開圓桌其餘直接做\n" % dup)
        # v0.4.1 反向 fixture：.py 註解引用 R5 講的是完全不同的事 —— 不得進 D10
        w("alpha/helper.py",
          "# R5：這裡只是程式碼註解在引用規則五順便講實作細節跟定義無關\n"
          "def helper():\n    return 0\n")
        # beta 的 R5 是**另一個命名空間**的規則，內容完全不同 —— 不得被判成漂移
        w("beta/README.md",
          "%s\nv0.1.0\nR5：本模組的第五條規則規定所有輸出必須先寫入暫存區再落盤\n" % dup)
        w("beta/thing_gate.py",
          "def _selftest():\n    return 0\n\n"
          "def big():\n" + "    x = 1\n" * 120)
        w("beta/ledger.md", "# 裁決台帳\n| 規則 A | 2026 | ⬜ 待建 | doc |\n")

        rep = scan(tmp)
        dims = {f["dim"] for f in rep["findings"]}

        check("D1 duplication detected", "D1" in dims)
        check("D2 naming rivalry detected", "D2" in dims)
        check("D4 long function detected", any(
            f["dim"] == "D4" and "函數過長" in f["title"] for f in rep["findings"]))
        check("D7 broken link detected", "D7" in dims)
        check("D8 version drift detected", "D8" in dims)
        # dogfood 回歸（三連踩，見 _versions docstring）
        check("D8 ignores bare numeric constants",
              _versions("THRESHOLD = 0.30\nratio 1.0\n") == set())
        check("D8 ignores prose mentions of a version",
              _versions("算出全庫最新 v9.0.0 這種不存在的版本\n"
                        "為什麼 v0.4 要有這支檔\n") == set())
        check("D8 accepts declarations only",
              _versions("## v0.7.3 - notes") == {(0, 7, 3)}
              and _versions("version: 0.5.1") == {(0, 5, 1)}
              and _versions('__version__ = "1.2.3"') == {(1, 2, 3)})
        check("D10 rule drift detected (R5 says two different things)",
              any(f["dim"] == "D10" and "R5" in f["title"] for f in rep["findings"]))
        # dogfood 回歸：跨命名空間撞同一個 ID **不得**判成漂移
        d10 = [f for f in rep["findings"] if f["dim"] == "D10"]
        check("D10 scoped to one namespace (no cross-skill collision)",
              all("alpha" in f["title"] for f in d10))
        check("D10 ignores changelog rows", not any(
            "訪談落地" in f["detail"] for f in d10))
        # dogfood 回歸：.py 原始碼裡的字串不是 markdown 連結
        check("D7 skips non-markdown files", all(
            f["where"].endswith(".md")
            for f in rep["findings"] if f["dim"] == "D7"))
        # v0.4.1 外部 review 回歸：中文偽連結記法≠斷鏈；.py 引用≠競爭定義
        check("D7 skips prose pseudo-links", not any(
            "摳luma" in f["detail"] for f in rep["findings"] if f["dim"] == "D7"))
        check("D10 ignores code-file rule citations", not any(
            "helper.py" in f["where"] for f in rep["findings"] if f["dim"] == "D10"))
        check("D11 island detected", "D11" in dims)
        check("D12 gate without corpus detected", any(
            f["dim"] == "D12" and "corpus" in f["title"] for f in rep["findings"]))
        check("D13 unlanded ruling detected", "D13" in dims)
        check("D7 is CRITICAL", all(
            f["severity"] == "CRITICAL" for f in rep["findings"] if f["dim"] == "D7"))
        check("findings sorted by severity", [SEVERITY_ORDER[f["severity"]]
                                              for f in rep["findings"]]
              == sorted(SEVERITY_ORDER[f["severity"]] for f in rep["findings"]))
        check("report renders", len(format_report(rep)) > 200)
        check("report is json-serializable", bool(json.dumps(rep["findings"])))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 反向對照：乾淨專案不得亂報（誤殺比漏抓貴 — M114 rule 1）
    tmp2 = tempfile.mkdtemp(prefix="cleanupclean_")
    try:
        p = os.path.join(tmp2, "solo")
        os.makedirs(p)
        with io.open(os.path.join(p, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("# solo\n\n單一模組，簡短乾淨，沒有重複也沒有壞連結。\n")
        rep2 = scan(tmp2)
        check("clean project produces no findings", not rep2["findings"])
    finally:
        shutil.rmtree(tmp2, ignore_errors=True)

    # 真 corpus 級回歸（自家 D12 教條）：in-process 全綠 ≠ 當工具跑不炸。
    # v0.4 翻車實錄：selftest 17/17 綠，真掃第一發 UnicodeEncodeError ——
    # findings 含簡體 '户'（户），cp950 stdout 編不出來。這裡把掃描器當
    # **子行程**跑（stdout=pipe，Windows 預設 ANSI code page），fixture 塞
    # 會進 findings 的簡體字，斷言 returncode 0。
    import subprocess
    tmp3 = tempfile.mkdtemp(prefix="cleanupcp950_")
    try:
        p3 = os.path.join(tmp3, "gamma")
        os.makedirs(p3)
        with io.open(os.path.join(p3, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("# gamma\n[用户资料](./缺失的档案.md)\n")
        env = os.environ.copy()
        env.pop("PYTHONIOENCODING", None)   # 還原「沒人幫忙救」的真實終端
        env.pop("PYTHONUTF8", None)
        proc = subprocess.run(
            [sys.executable, os.path.abspath(__file__), tmp3],
            capture_output=True, env=env, timeout=60)
        check("subprocess survives cp950 console (real-corpus)",
              proc.returncode == 0)
    finally:
        shutil.rmtree(tmp3, ignore_errors=True)

    print("-" * 62)
    if failed:
        print("SELFTEST RED: %d failed" % len(failed))
        for f in failed:
            print("  - " + f)
        return 1
    print("SELFTEST GREEN: all checks passed")
    return 0


# ═══════════════════════════════════════════════ CLI

def main(argv):
    if "--selftest" in argv:
        return _selftest()
    args = [a for a in argv[1:] if not a.startswith("--")]
    if not args:
        print("usage: python cleanup_scan.py <root> [--json out.json] [--max-files N]")
        print("       python cleanup_scan.py --selftest")
        return 2
    root = args[0]
    if not os.path.isdir(root):
        print("not a directory: %s" % root)
        return 2
    mx = 400
    if "--max-files" in argv:
        try:
            mx = int(argv[argv.index("--max-files") + 1])
        except (IndexError, ValueError):
            pass
    rep = scan(root, mx)
    print(format_report(rep))
    if "--json" in argv:
        try:
            out = argv[argv.index("--json") + 1]
            with io.open(out, "w", encoding="utf-8") as f:
                json.dump(rep, f, ensure_ascii=False, indent=2)
            print("\njson written: %s" % out)
        except (IndexError, OSError):
            print("\n--json needs a writable path")
    return 0


if __name__ == "__main__":
    # findings 內容必然含中文（規則描述/檔案行），cp950 終端遇簡體字元會炸。
    # M114 同形實例：selftest 掃合成 ASCII 專案全綠，真掃第一發 UnicodeEncodeError。
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    raise SystemExit(main(sys.argv))
