#!/usr/bin/env python3
"""Cross-platform, read-only audit engine for code-cleanup-helper."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


TEXT_EXTENSIONS = {
    ".md", ".txt", ".py", ".js", ".ts", ".tsx", ".jsx", ".json",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".html", ".css", ".csv",
}

DEFAULT_CONFIG: dict[str, Any] = {
    "exclude": [
        ".git/**", "node_modules/**", ".venv/**", "venv/**", "dist/**",
        "build/**", "__pycache__/**", "*.pyc",
    ],
    "thresholds": {
        "skill_warning": 200,
        "skill_severe": 400,
        "reference_warning": 400,
        "reference_severe": 800,
        "code_warning": 500,
        "code_severe": 1000,
    },
    "duplicate_min_chars": 80,
    "duplicate_min_occurrences": 3,
    "length_exceptions": [],
    "navigation_exceptions": [],
    "id_definition_scopes": {},
    "range_claim_scopes": {},
    "sync": {"public_root": None, "ignore": [], "normalize_text": True},
    "drift_assertions": [],
    "privacy": {"tokens": [], "patterns": [], "allow": []},
}


@dataclass
class Finding:
    dimension: int
    status: str
    code: str
    message: str
    path: str | None = None
    line: int | None = None
    details: dict[str, Any] | None = None


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(root: Path, config_path: Path | None) -> tuple[dict[str, Any], Path | None]:
    candidate = config_path or (root / "audit.config.json")
    if not candidate.exists():
        return DEFAULT_CONFIG, None
    data = json.loads(candidate.read_text(encoding="utf-8-sig"))
    return deep_merge(DEFAULT_CONFIG, data), candidate


def is_excluded(relative: str, patterns: Iterable[str]) -> bool:
    normalized = relative.replace("\\", "/")
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in patterns)


def collect_files(root: Path, config: dict[str, Any]) -> list[Path]:
    files: list[Path] = []
    resolved_root = root.resolve()
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        try:
            path.resolve().relative_to(resolved_root)
        except ValueError:
            continue
        relative = path.relative_to(root).as_posix()
        if not is_excluded(relative, config["exclude"]):
            files.append(path)
    return sorted(files)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def file_inventory(root: Path, files: list[Path]) -> list[dict[str, Any]]:
    inventory = []
    for path in files:
        text = read_text(path)
        inventory.append({
            "path": rel(root, path),
            "lines": len(text.splitlines()),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    return inventory


def normalized_paragraphs(text: str, min_chars: int) -> list[tuple[int, str, str]]:
    paragraphs: list[tuple[int, str, str]] = []
    block: list[str] = []
    start = 1
    in_fence = False
    lines = text.splitlines()
    for line_no, line in enumerate(lines + [""], start=1):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line.strip():
            if not block:
                start = line_no
            block.append(line.strip())
            continue
        if block:
            raw = " ".join(block)
            normalized = re.sub(r"\s+", " ", raw).strip()
            if len(normalized) >= min_chars and not normalized.startswith("|"):
                paragraphs.append((start, normalized.casefold(), raw))
            block = []
    return paragraphs


def audit_duplicates(root: Path, files: list[Path], config: dict[str, Any]) -> list[Finding]:
    buckets: dict[str, list[tuple[str, int, str]]] = defaultdict(list)
    for path in files:
        if path.suffix.lower() not in {".md", ".txt"}:
            continue
        for line, normalized, raw in normalized_paragraphs(
            read_text(path), int(config["duplicate_min_chars"])
        ):
            buckets[normalized].append((rel(root, path), line, raw))
    findings: list[Finding] = []
    minimum = int(config["duplicate_min_occurrences"])
    for matches in buckets.values():
        if len(matches) < minimum or len({item[0] for item in matches}) < 2:
            continue
        sample = matches[0][2][:140]
        findings.append(Finding(
            1, "FAIL", "duplicate-block",
            f"相同長段落出現 {len(matches)} 次：{sample}",
            matches[0][0], matches[0][1],
            {"locations": [{"path": p, "line": line} for p, line, _ in matches]},
        ))
    if not findings:
        findings.append(Finding(1, "PASS", "duplicate-block", "未發現跨檔案重複長段落"))
    return findings


ID_PATTERN = re.compile(r"^#{2,6}\s+(R\d+|F\d+(?:[a-z]|\s+mini)?|Case\s+\d+)\s*[：｜:]", re.I | re.M)


def audit_ids_and_ranges(root: Path, files: list[Path], config: dict[str, Any]) -> list[Finding]:
    locations: dict[str, list[tuple[str, int]]] = defaultdict(list)
    combined: list[tuple[Path, str]] = []
    definition_scopes = config.get("id_definition_scopes", {})
    range_scopes = config.get("range_claim_scopes", {})
    for path in files:
        if path.suffix.lower() != ".md":
            continue
        text = read_text(path)
        combined.append((path, text))
        for match in ID_PATTERN.finditer(text):
            token = re.sub(r"\s+", "-", match.group(1).upper())
            key = "CASE" if token.startswith("CASE") else token[0]
            scoped_globs = definition_scopes.get(key)
            relative = rel(root, path)
            if scoped_globs is not None and not any(fnmatch.fnmatch(relative, pattern) for pattern in scoped_globs):
                continue
            line = text.count("\n", 0, match.start()) + 1
            locations[token].append((relative, line))

    findings: list[Finding] = []
    for token, spots in locations.items():
        if len(spots) > 1 and not token.endswith("-MINI"):
            findings.append(Finding(
                2, "FAIL", "duplicate-id", f"編號 {token} 重複定義 {len(spots)} 次",
                spots[0][0], spots[0][1], {"locations": spots},
            ))

    maxima = {"R": 0, "F": 0, "CASE": 0}
    for token in locations:
        match = re.search(r"\d+", token)
        if not match:
            continue
        value = int(match.group())
        key = "CASE" if token.startswith("CASE") else token[0]
        maxima[key] = max(maxima[key], value)

    range_patterns = {
        "R": re.compile(r"R1\s*[-–—]\s*R?(\d+)", re.I),
        "F": re.compile(r"F1\s*[-–—]\s*F?(\d+)", re.I),
        "CASE": re.compile(r"Cases?\s+1\s*[-–—]\s*(\d+)", re.I),
    }
    for path, text in combined:
        for key, pattern in range_patterns.items():
            scoped_globs = range_scopes.get(key)
            relative = rel(root, path)
            if scoped_globs is not None and not any(fnmatch.fnmatch(relative, item) for item in scoped_globs):
                continue
            for match in pattern.finditer(text):
                declared = int(match.group(1))
                if maxima[key] and declared != maxima[key]:
                    line = text.count("\n", 0, match.start()) + 1
                    findings.append(Finding(
                        8, "FAIL", "range-drift",
                        f"{match.group(0)} 與實際最大編號 {maxima[key]} 不一致",
                        relative, line,
                        {"declared": declared, "actual": maxima[key], "type": key},
                    ))
    if not any(item.dimension == 2 for item in findings):
        findings.append(Finding(2, "PASS", "heading-ids", "未發現重複規則／公式／案例 ID"))
    if not any(item.dimension == 8 for item in findings):
        findings.append(Finding(8, "PASS", "range-drift", "編號範圍與實際最大 ID 一致"))
    return findings


def audit_lengths(root: Path, inventory: list[dict[str, Any]], config: dict[str, Any]) -> list[Finding]:
    t = config["thresholds"]
    exceptions = config.get("length_exceptions", [])
    findings: list[Finding] = []
    for item in inventory:
        path = item["path"]
        if any(fnmatch.fnmatch(path, pattern) for pattern in exceptions):
            continue
        lines = item["lines"]
        parts = Path(path).parts
        if Path(path).name == "SKILL.md":
            warning, severe = t["skill_warning"], t["skill_severe"]
        elif "references" in parts and path.endswith(".md"):
            warning, severe = t["reference_warning"], t["reference_severe"]
        elif Path(path).suffix.lower() in {".py", ".js", ".ts", ".tsx", ".jsx"}:
            warning, severe = t["code_warning"], t["code_severe"]
        else:
            continue
        if lines > severe:
            findings.append(Finding(4, "FAIL", "file-too-long", f"{lines} 行，超過嚴重線 {severe}", path))
        elif lines > warning:
            findings.append(Finding(4, "FAIL", "file-long", f"{lines} 行，超過警告線 {warning}", path))
    if not findings:
        findings.append(Finding(4, "PASS", "file-lengths", "所有受管檔案皆在長度警告線內"))
    return findings


MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def looks_like_local_path(target: str) -> bool:
    """Avoid treating prose notes such as ``[label](某段筆記)`` as files."""
    clean = target.split("#", 1)[0].split("?", 1)[0]
    if any(separator in clean for separator in ("/", "\\")):
        return True
    if Path(clean).suffix:
        return True
    return clean.upper() in {"LICENSE", "README", "CHANGELOG", "CONTRIBUTING"}


def audit_links(root: Path, files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in files:
        if path.suffix.lower() != ".md":
            continue
        for line_no, line in enumerate(read_text(path).splitlines(), start=1):
            for match in MARKDOWN_LINK.finditer(line):
                target = match.group(1).strip().strip("<>")
                if target.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                target_path = target.split("#", 1)[0]
                if not target_path:
                    continue
                resolved = (path.parent / target_path).resolve()
                if not resolved.exists() and looks_like_local_path(target):
                    findings.append(Finding(
                        7, "FAIL", "broken-link", f"本地 Markdown 連結不存在：{target}",
                        rel(root, path), line_no,
                    ))
    if not findings:
        findings.append(Finding(7, "PASS", "markdown-links", "本地 Markdown 連結完整"))
    return findings


def audit_assertions(root: Path, files: list[Path], config: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    file_map = {rel(root, path): read_text(path) for path in files}
    assertions = config.get("drift_assertions", [])
    for assertion in assertions:
        assertion_id = assertion.get("id", "custom-assertion")
        try:
            pattern = re.compile(assertion["pattern"], re.I | re.M)
        except (KeyError, re.error) as exc:
            findings.append(Finding(
                8, "FAIL", "assertion-pattern-invalid",
                f"drift assertion {assertion_id} regex 無效：{exc}",
                details={"assertion_id": assertion_id},
            ))
            continue
        globs = assertion.get("files", ["**/*"])
        matches: list[dict[str, Any]] = []
        for path, text in file_map.items():
            if not any(fnmatch.fnmatch(path, glob) for glob in globs):
                continue
            for match in pattern.finditer(text):
                matches.append({"path": path, "line": text.count("\n", 0, match.start()) + 1, "text": match.group(0)})
        expected = int(assertion.get("expected_count", 0))
        if len(matches) != expected:
            findings.append(Finding(
                8, "FAIL", assertion_id,
                assertion.get("message", f"自訂漂移檢查失敗：預期 {expected} 筆，實際 {len(matches)} 筆"),
                matches[0]["path"] if matches else None,
                matches[0]["line"] if matches else None,
                {"expected_count": expected, "actual_count": len(matches), "matches": matches},
            ))
        else:
            findings.append(Finding(8, "PASS", assertion_id, assertion.get("pass_message", f"{assertion_id} 通過")))
    return findings


def audit_skill_package(root: Path, files: list[Path], config: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    skills = [path for path in files if path.name == "SKILL.md"]
    for skill in skills:
        text = read_text(skill)
        frontmatter = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
        body = frontmatter.group(1) if frontmatter else ""
        name_match = re.search(r"^name:\s*([^\n]+)", body, re.M)
        description_match = re.search(r"^description:\s*(\S.*)$", body, re.M)
        relative_skill = rel(root, skill)
        if not frontmatter or not name_match or not description_match:
            findings.append(Finding(
                9, "FAIL", "skill-frontmatter",
                "SKILL.md 缺少有效 name／description frontmatter", relative_skill, 1,
            ))
        else:
            name = name_match.group(1).strip().strip("\"'")
            agents = skill.parent / "agents" / "openai.yaml"
            if not agents.exists():
                findings.append(Finding(
                    9, "FAIL", "agents-metadata", "缺少 agents/openai.yaml",
                    rel(root, skill.parent),
                ))
            elif f"${name}" not in read_text(agents):
                findings.append(Finding(
                    9, "FAIL", "default-prompt",
                    f"agents/openai.yaml 的 default_prompt 未提及 ${name}", rel(root, agents),
                ))
    navigation_exceptions = config.get("navigation_exceptions", [])
    for path in files:
        relative = rel(root, path)
        if "references" not in Path(relative).parts or path.suffix.lower() != ".md":
            continue
        if any(fnmatch.fnmatch(relative, pattern) for pattern in navigation_exceptions):
            continue
        lines = read_text(path).splitlines()
        if len(lines) > 100:
            top = "\n".join(lines[:60]).casefold()
            if not any(word in top for word in ("目錄", "table of contents", "導航", "索引")):
                findings.append(Finding(9, "FAIL", "reference-navigation", f"{len(lines)} 行但前 60 行沒有目錄／導航", relative))

    privacy = config.get("privacy", {})
    allow = privacy.get("allow", [])
    for token in privacy.get("tokens", []):
        pattern = re.compile(re.escape(token), re.I)
        for path in files:
            relative = rel(root, path)
            if any(fnmatch.fnmatch(relative, item) for item in allow):
                continue
            text = read_text(path)
            match = pattern.search(text)
            if match:
                findings.append(Finding(
                    9, "FAIL", "privacy-token", f"公開候選檔案含個人 token：{token}",
                    relative, text.count("\n", 0, match.start()) + 1,
                ))
    for raw_pattern in privacy.get("patterns", []):
        try:
            pattern = re.compile(raw_pattern, re.I)
        except re.error as exc:
            findings.append(Finding(
                9, "FAIL", "privacy-pattern-invalid", f"privacy regex 無效：{exc}",
                details={"pattern": raw_pattern},
            ))
            continue
        for path in files:
            relative = rel(root, path)
            if any(fnmatch.fnmatch(relative, item) for item in allow):
                continue
            text = read_text(path)
            match = pattern.search(text)
            if match:
                findings.append(Finding(
                    9, "FAIL", "privacy-pattern", f"公開候選檔案符合隱私 pattern：{raw_pattern}",
                    relative, text.count("\n", 0, match.start()) + 1,
                ))
    if not findings:
        findings.append(Finding(9, "PASS", "skill-package", "Skill metadata、reference 導航與隱私規則通過"))
    return findings


def audit_sync(root: Path, config: dict[str, Any]) -> list[Finding]:
    sync = config.get("sync", {})
    public_value = sync.get("public_root")
    if not public_value:
        return [Finding(5, "NOT_CHECKED", "sync-unconfigured", "未設定 sync.public_root")]
    public_root = Path(public_value).expanduser()
    if not public_root.is_absolute():
        public_root = (root / public_root).resolve()
    if not public_root.exists():
        return [Finding(5, "NOT_CHECKED", "sync-root-missing", f"公開版路徑不存在：{public_root}")]
    ignore = sync.get("ignore", [])
    normalize_text = bool(sync.get("normalize_text", True))
    findings: list[Finding] = []
    for private in collect_files(root, config):
        relative = rel(root, private)
        if any(fnmatch.fnmatch(relative, item) for item in ignore):
            continue
        public = public_root / relative
        if not public.exists():
            findings.append(Finding(5, "FAIL", "sync-missing", "公開版缺少檔案", relative))
        elif (
            read_text(private) != read_text(public)
            if normalize_text else private.read_bytes() != public.read_bytes()
        ):
            findings.append(Finding(5, "FAIL", "sync-diff", "私版與公開版內容不同", relative))
    if not findings:
        findings.append(Finding(5, "PASS", "sync", "私版與公開版同步"))
    return findings


VERSION_PATTERN = re.compile(r"\bv(\d+)\.(\d+)(?:\.(\d+))?\b", re.I)
DECLARED_SEMVER_PATTERN = re.compile(r"\bv?(\d+)\.(\d+)(?:\.(\d+))?\b", re.I)
VERSION_DECLARATION = re.compile(
    r"(?:^\s*#{1,6}\s*v\d+\.\d+(?:\.\d+)?\b|"
    r"(?:目前版本|current version|version\s*[:=]|__version__\s*=).*?v?\d+\.\d+(?:\.\d+)?)",
    re.I | re.M,
)


def version_tuple(value: str) -> tuple[int, int, int]:
    match = VERSION_PATTERN.search(value)
    return tuple(int(part or 0) for part in match.groups()) if match else (0, 0, 0)


def declared_versions(text: str) -> list[str]:
    versions: list[str] = []
    for declaration in VERSION_DECLARATION.finditer(text):
        match = DECLARED_SEMVER_PATTERN.search(declaration.group(0))
        if match:
            versions.append("v" + ".".join(part or "0" for part in match.groups()))
    return versions


def run_command(args: list[str], cwd: Path) -> tuple[bool, str]:
    try:
        completed = subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    return completed.returncode == 0, completed.stdout.strip() or completed.stderr.strip()


def audit_release(root: Path) -> list[Finding]:
    if not (root / ".git").exists():
        return [Finding(6, "NOT_CHECKED", "git-unavailable", "目標不是 Git repository；release 一致性未檢查")]
    ok, output = run_command(["git", "tag", "--list"], root)
    if not ok:
        return [Finding(6, "NOT_CHECKED", "git-tag-error", f"無法讀取 git tags：{output}")]
    tags = [line for line in output.splitlines() if VERSION_PATTERN.search(line)]
    if not tags:
        return [Finding(6, "NOT_CHECKED", "no-version-tags", "repository 沒有 semver tag")]
    latest = max(tags, key=version_tuple)
    latest_tuple = version_tuple(latest)
    findings: list[Finding] = []
    for filename in ("CHANGELOG.md", "README.md"):
        path = root / filename
        if not path.exists():
            continue
        versions = declared_versions(read_text(path))
        if not versions:
            findings.append(Finding(6, "NOT_CHECKED", "release-doc-version-missing", f"{filename} 沒有可辨識的版本宣告", filename))
            continue
        document_latest = max(versions, key=version_tuple)
        document_tuple = version_tuple(document_latest)
        if document_tuple < latest_tuple:
            findings.append(Finding(6, "FAIL", "release-doc-behind", f"{filename} 最新版本 {document_latest} 落後 tag {latest}", filename))
        elif document_tuple > latest_tuple:
            findings.append(Finding(6, "FAIL", "release-tag-behind", f"{filename} 最新版本 {document_latest} 尚無對應 tag（latest {latest}）", filename))
    if not findings:
        findings.append(Finding(6, "PASS", "release-docs", f"release 文件與 latest tag {latest} 對齊"))
    return findings


def run_audit(root: Path, mode: str, config_path: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Target directory does not exist: {root}")
    config, loaded_config = load_config(root, config_path)
    files = collect_files(root, config)
    inventory = file_inventory(root, files)
    findings: list[Finding] = []
    if mode in {"a", "all"}:
        findings.extend(audit_duplicates(root, files, config))
        findings.extend(audit_ids_and_ranges(root, files, config))
        findings.extend(audit_lengths(root, inventory, config))
    if mode in {"b", "all"}:
        findings.extend(audit_sync(root, config))
        findings.extend(audit_release(root))
        findings.extend(audit_links(root, files))
        if mode == "b":
            findings.extend(item for item in audit_ids_and_ranges(root, files, config) if item.dimension == 8)
        findings.extend(audit_assertions(root, files, config))
        findings.extend(audit_skill_package(root, files, config))

    counts = Counter(item.status for item in findings)
    return {
        "schema_version": "1.0",
        "target": str(root),
        "mode": mode,
        "config": str(loaded_config) if loaded_config else None,
        "summary": {
            "files": len(inventory),
            "lines": sum(item["lines"] for item in inventory),
            "bytes": sum(item["bytes"] for item in inventory),
            "pass": counts["PASS"],
            "fail": counts["FAIL"],
            "not_checked": counts["NOT_CHECKED"],
        },
        "inventory": inventory,
        "findings": [asdict(item) for item in findings],
    }


def render_human(report: dict[str, Any], max_findings: int = 30) -> str:
    summary = report["summary"]
    lines = [
        f"=== Cleanup Audit — {report['target']} ===",
        f"files={summary['files']} lines={summary['lines']} bytes={summary['bytes']}",
        f"PASS={summary['pass']} FAIL={summary['fail']} NOT_CHECKED={summary['not_checked']}",
        "",
    ]
    actionable = [item for item in report["findings"] if item["status"] != "PASS"]
    if not actionable:
        lines.append("PASS｜沒有需要處理的發現")
    for item in actionable[:max_findings]:
        location = ""
        if item.get("path"):
            location = f"｜{item['path']}"
            if item.get("line"):
                location += f":{item['line']}"
        lines.append(f"{item['status']}｜D{item['dimension']}｜{item['code']}｜{item['message']}{location}")
    hidden = len(actionable) - max_findings
    if hidden > 0:
        lines.append(f"...另有 {hidden} 筆；改用 --format json 查看完整內容")
    return "\n".join(lines)
