#!/usr/bin/env python3
"""
Test: Can an AI (Gemini) discover all skill .md files from the AirSkill index?

Flow:
1. Build expected set of Direct Links from filesystem (skills/**/*.md).
2. Give Gemini the root index content + group index content(s).
3. Ask Gemini to list every Direct Link it would fetch to get all skills.
4. Parse Gemini response and compare to expected.
"""

import csv
import os
import re
import sys
from pathlib import Path

# Add project root for imports
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Load .env from project root if present
_env = ROOT / ".env"
if _env.is_file():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env)
    except ImportError:
        pass

SKILLS_DIR = ROOT / "skills"
INDEX_HTML = ROOT / "index.html"
BASE_URL = "https://skill.ruska.cn/skills"

# build.py 里无 overview 时的通用 Summary；主索引出现此句说明组行无意义，AI 无法判断该组用途
GENERIC_GROUP_SUMMARY = "Layered skill group. Fetch Direct Link for sub-skill index."


def get_expected_urls() -> set[str]:
    """All .md files under skills/ as full Direct Links."""
    expected = set()
    for path in sorted(SKILLS_DIR.rglob("*.md")):
        rel = path.relative_to(SKILLS_DIR)
        url = f"{BASE_URL}/{rel.as_posix()}"
        expected.add(url)
    return expected


def get_index_text() -> str:
    """Extract manifest text from index.html (<pre> body)."""
    raw = INDEX_HTML.read_text(encoding="utf-8")
    m = re.search(r"<pre>\s*([\s\S]*?)\s*</pre>", raw)
    if not m:
        return raw
    return m.group(1).strip()


def get_group_index_texts() -> list[tuple[str, str]]:
    """(group_name, content) for each skills/<group>/index.md."""
    out = []
    for d in SKILLS_DIR.iterdir():
        if not d.is_dir():
            continue
        idx = d / "index.md"
        if idx.is_file():
            out.append((d.name, idx.read_text(encoding="utf-8")))
    return out


def run_gemini(api_key: str, index_text: str, group_texts: list[tuple[str, str]]) -> str:
    """Call Gemini to extract all Direct Links from root + group indices."""
    try:
        import google.generativeai as genai
    except ImportError:
        raise RuntimeError("Install: pip install google-generativeai")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")

    prompt_parts = [
        "You are an AI agent using the AirSkill manifest. Your task: list every Direct Link (URL) that points to an .md file so that you could fetch all skills.",
        "",
        "Rules:",
        "- From the ROOT MANIFEST below, list every Direct Link from the table (Skill ID, Direct Link, Summary).",
        "- For any row whose Direct Link points to an index (e.g. .../memory-system/index.md), use the GROUP INDEX content provided below to list every Direct Link from that group's Sub-skills table.",
        "- Output only URLs, one per line. No other text.",
        "",
        "--- ROOT MANIFEST ---",
        index_text,
    ]
    for group_name, content in group_texts:
        prompt_parts.extend(["", f"--- GROUP INDEX: {group_name} (content of .../skills/{group_name}/index.md) ---", content])
    prompt_parts.append("")
    prompt_parts.append("--- END ---")
    prompt_parts.append("Output every skill Direct Link (one per line):")

    response = model.generate_content("\n".join(prompt_parts))
    if not response or not response.text:
        raise RuntimeError("Empty response from Gemini")
    return response.text


def parse_urls_from_response(text: str) -> set[str]:
    """Extract lines that look like https://skill.ruska.cn/skills/..."""
    urls = set()
    for line in text.strip().splitlines():
        line = line.strip()
        # Allow markdown links: [text](url) or bare url
        m = re.search(r"https://skill\.ruska\.cn/skills/[^\s\)]+", line)
        if m:
            url = m.group(0).rstrip(".,;)")
            urls.add(url)
    return urls


def parse_index_programmatically(index_text: str, group_texts: list[tuple[str, str]]) -> set[str]:
    """Parse root + group index text for Direct Links (no LLM). Validates manifest structure."""
    url_re = re.compile(r"https://skill\.ruska\.cn/skills/[^\s\|\)]+")
    found = set(url_re.findall(index_text))
    for _group, content in group_texts:
        found.update(url_re.findall(content))
    return {u.rstrip(".,;)") for u in found}


def get_expected_urls_by_group() -> dict[str, set[str]]:
    """Expected URLs per group (group name -> set of full URLs). Root-level skills in group ''."""
    by_group = {}
    for path in sorted(SKILLS_DIR.rglob("*.md")):
        rel = path.relative_to(SKILLS_DIR)
        url = f"{BASE_URL}/{rel.as_posix()}"
        parts = rel.parts
        group = "" if len(parts) == 1 else parts[0]
        if group not in by_group:
            by_group[group] = set()
        by_group[group].add(url)
    return by_group


def parse_urls_from_text(text: str) -> set[str]:
    url_re = re.compile(r"https://skill\.ruska\.cn/skills/[^\s\|\)]+")
    return {u.rstrip(".,;)") for u in url_re.findall(text)}


def parse_root_index_all_rows(index_text: str) -> list[tuple[str, str, str]]:
    """Parse root index table: all rows. Return [(skill_id, link, summary), ...]."""
    rows = []
    for line in index_text.splitlines():
        line = line.strip()
        if not line.startswith("|") or line == "| :--- | :--- | :--- |":
            continue
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if len(parts) < 3:
            continue
        skill_id, link, summary = parts[0], parts[1], parts[2]
        rows.append((skill_id, link, summary))
    return rows


def parse_root_index_group_rows(index_text: str) -> list[tuple[str, str]]:
    """Parse root index table for group rows (Direct Link ends with index.md). Return [(skill_id, summary), ...]."""
    rows = []
    for sid, link, summary in parse_root_index_all_rows(index_text):
        if "/index.md" in link or link.endswith("index.md"):
            rows.append((sid, summary))
    return rows


def parse_group_index_rows(content: str) -> list[tuple[str, str, str]]:
    """Parse group index Sub-skills table. Return [(skill_id, link, summary), ...]."""
    rows = []
    for line in content.splitlines():
        line = line.strip()
        if not line.startswith("|") or line == "| :--- | :--- | :--- |":
            continue
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if len(parts) < 3:
            continue
        skill_id, link, summary = parts[0], parts[1], parts[2]
        rows.append((skill_id, link, summary))
    return rows


def build_skill_assessment(
    expected: set[str],
    parsed: set[str],
    index_text: str,
    group_texts: list[tuple[str, str]],
) -> list[dict]:
    """Build per-skill assessment: skill, 描述, AI是否能理解, 为什么说能理解和调用, 描述有效性评分 (1-5)."""
    # url -> (skill_id, summary); skill_id from link path (e.g. api-docs, memory-system/retain)
    url_to_info = {}
    for sid, link, summary in parse_root_index_all_rows(index_text):
        url = link.rstrip(".,;)")
        url_to_info[url] = (sid, summary)
    for _group, content in group_texts:
        for sid, link, summary in parse_group_index_rows(content):
            url = link.rstrip(".,;)")
            url_to_info[url] = (sid, summary)

    generic_summaries = {
        sid for sid, summary in parse_root_index_group_rows(index_text)
        if summary.strip() == GENERIC_GROUP_SUMMARY
    }

    result = []
    for url in sorted(expected):
        # skill_id from URL path: .../skills/api-docs.md -> api-docs; .../memory-system/retain.md -> memory-system/retain
        skill_id_from_url = url.replace(BASE_URL + "/", "").replace(".md", "")
        info = url_to_info.get(url)
        if not info:
            result.append({
                "skill": skill_id_from_url,
                "description": "(未在索引中)",
                "ai_understandable": "不能",
                "reason": "未出现在主索引或组索引中，AI 无法发现该技能。",
                "score": 1,
            })
            continue
        sid, summary = info
        in_manifest = url in parsed
        is_group_row = url.endswith("/index.md")
        is_generic = is_group_row and sid in generic_summaries

        if not in_manifest:
            result.append({
                "skill": sid,
                "description": summary[:200] + ("…" if len(summary) > 200 else ""),
                "ai_understandable": "不能",
                "reason": "未出现在索引内容中，AI 无法发现。",
                "score": 1,
            })
        elif is_generic:
            result.append({
                "skill": sid,
                "description": summary[:200] + ("…" if len(summary) > 200 else ""),
                "ai_understandable": "不能",
                "reason": "组行使用通用 Summary，AI 无法判断该组用途，无法选型调用。",
                "score": 2,
            })
        else:
            desc_short = summary[:200] + ("…" if len(summary) > 200 else "")
            if is_group_row:
                reason = "已列入主索引组行，Summary 具体，AI 可据此判断组用途并进入组索引选型调用。"
            else:
                reason = "已列入主索引或组索引，Direct Link 可直达，Summary 可区分用途，AI 可选型并调用。"
            # 描述有效性: 5=具体可区分、可选型, 4=清晰, 3=一般
            score = 5 if len(summary) > 80 else 4
            result.append({
                "skill": sid,
                "description": desc_short,
                "ai_understandable": "能",
                "reason": reason,
                "score": score,
            })
    return result


def write_result_file(
    expected: set[str],
    parsed: set[str],
    by_group: dict[str, set[str]],
    group_texts: list[tuple[str, str]],
    group_rows: list[tuple[str, str]],
    assessment: list[dict],
    gemini_found: set[str] | None,
    gemini_error: str | None,
) -> None:
    """Write tests/output/discovery_result.md (with skill assessment table) and discovery_result.csv."""
    out_dir = ROOT / "tests" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / "discovery_result.md"
    csv_path = out_dir / "discovery_result.csv"

    # Columns: skill, skill的描述, AI是否能理解, 为什么说能理解和调用, skill描述有效性的评分
    col_skill = "skill"
    col_desc = "skill的描述"
    col_understand = "AI是否能理解"
    col_reason = "为什么说能理解和调用"
    col_score = "skill描述有效性评分"

    # --- MD: title + table ---
    lines = [
        "# AirSkill 技能发现与描述有效性评估",
        "",
        "每行一个技能；列：技能 ID、描述、AI 是否能理解并调用、理由、描述有效性评分（1–5）。",
        "",
        "| " + " | ".join([col_skill, col_desc, col_understand, col_reason, col_score]) + " |",
        "| " + " | ".join(["---"] * 5) + " |",
    ]
    for row in assessment:
        # Escape pipe in description/reason for MD
        desc = (row["description"] or "").replace("|", "\\|").replace("\n", " ")
        reason = (row["reason"] or "").replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {row['skill']} | {desc} | {row['ai_understandable']} | {reason} | {row['score']} |")
    lines.extend(["", "---", ""])

    # --- MD: 汇总 (原 §1, 1.5, 2, 3) ---
    lines.extend([
        "## 汇总",
        "",
        "### 1. Root index (index.html)",
        "",
        f"- **Expected total URLs** (from filesystem): {len(expected)}",
        f"- **Parsed from manifest** (root + all group index content): {len(parsed)}",
    ])
    missing_manifest = expected - parsed
    if missing_manifest:
        lines.append("- **Status**: FAIL — index content does not list all expected URLs.")
        lines.append("- **Missing in manifest**:")
        for u in sorted(missing_manifest):
            lines.append(f"  - `{u}`")
    else:
        lines.append("- **Status**: PASS — all expected URLs appear in root or group index content.")
    lines.extend(["", "### 1.5 Group row summaries (root index)", ""])
    generic_groups = [sid for sid, summary in group_rows if summary.strip() == GENERIC_GROUP_SUMMARY]
    if generic_groups:
        lines.append("- **Status**: FAIL — the following group row(s) use the generic Summary:")
        for g in generic_groups:
            lines.append(f"  - `{g}`")
    else:
        lines.append("- **Status**: PASS — all group rows have a non-generic Summary.")
    lines.extend(["", "### 2. Per-group index (skills/<group>/index.md)", ""])
    for group_name, content in group_texts:
        expected_in_group = by_group.get(group_name, set())
        index_url = f"{BASE_URL}/{group_name}/index.md"
        expected_listed = expected_in_group - {index_url}
        found_in_content = parse_urls_from_text(content)
        listed_in_index = found_in_content & expected_listed
        missing_in_group = expected_listed - found_in_content
        status = "PASS" if not missing_in_group else "FAIL"
        lines.append(f"- **{group_name}**: {status} (expected {len(expected_listed)} sub-skills, listed {len(listed_in_index)})")
    lines.extend(["", "### 3. Gemini discovery (optional)", ""])
    if gemini_error:
        lines.append(f"- **Status**: ERROR — {gemini_error}")
    elif gemini_found is not None:
        missing_g = expected - gemini_found
        extra_g = gemini_found - expected
        if not missing_g and not extra_g:
            lines.append("- **Status**: PASS — AI reported all expected URLs and no spurious ones.")
        else:
            lines.append("- **Status**: FAIL")
            if missing_g:
                lines.append(f"- **Missing**: {len(missing_g)}")
            if extra_g:
                lines.append(f"- **Extra**: {len(extra_g)}")
    else:
        lines.append("- **Status**: Skipped (GEMINI_API_KEY not set).")
    lines.append("")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # --- CSV ---
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([col_skill, col_desc, col_understand, col_reason, col_score])
        for row in assessment:
            w.writerow([
                row["skill"],
                row["description"] or "",
                row["ai_understandable"],
                row["reason"] or "",
                row["score"],
            ])

    print("Result written to:", md_path, "and", csv_path)


def main() -> int:
    expected = get_expected_urls()
    by_group = get_expected_urls_by_group()
    index_text = get_index_text()
    group_texts = get_group_index_texts()

    print("Expected URLs (from filesystem):", len(expected))

    # 1) Programmatic parse (no API): index + group index must contain all expected
    parsed = parse_index_programmatically(index_text, group_texts)
    missing_in_manifest = expected - parsed
    group_rows = parse_root_index_group_rows(index_text)
    generic_groups = [sid for sid, summary in group_rows if summary.strip() == GENERIC_GROUP_SUMMARY]

    assessment = build_skill_assessment(expected, parsed, index_text, group_texts)

    if missing_in_manifest:
        print("FAIL (manifest): Index content does not list these URLs:", file=sys.stderr)
        for u in sorted(missing_in_manifest):
            print("  ", u, file=sys.stderr)
        write_result_file(expected, parsed, by_group, group_texts, group_rows, assessment, None, None)
        return 1
    if generic_groups:
        print("FAIL (group summaries): Root index group row(s) use generic Summary; AI cannot tell what the group is for:", generic_groups, file=sys.stderr)
    print("PASS (manifest): All expected URLs appear in index / group index content.")

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    gemini_found = None
    gemini_error = None

    if api_key:
        try:
            response_text = run_gemini(api_key, index_text, group_texts)
            gemini_found = parse_urls_from_response(response_text)
            print("URLs Gemini reported:", len(gemini_found))
        except Exception as e:
            gemini_error = str(e)
            print("Gemini error:", e, file=sys.stderr)
            write_result_file(expected, parsed, by_group, group_texts, group_rows, assessment, None, gemini_error)
            return 0  # index build checks passed; Gemini optional
    else:
        print("Set GEMINI_API_KEY to run Gemini discovery test (optional).")

    write_result_file(expected, parsed, by_group, group_texts, group_rows, assessment, gemini_found, gemini_error)

    if generic_groups:
        return 1

    if gemini_found is not None:
        missing = expected - gemini_found
        extra = gemini_found - expected
        if not missing and not extra:
            print("PASS (Gemini): AI discovered all skill .md files and no spurious URLs.")
            return 0
        if missing:
            print("FAIL (Gemini): Missing URLs (expected but not reported by AI):", file=sys.stderr)
            for u in sorted(missing):
                print("  ", u, file=sys.stderr)
        if extra:
            print("INFO: Extra URLs (reported but not under skills/):", file=sys.stderr)
            for u in sorted(extra)[:20]:
                print("  ", u, file=sys.stderr)
            if len(extra) > 20:
                print("  ... and", len(extra) - 20, "more", file=sys.stderr)
        return 1 if missing else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
