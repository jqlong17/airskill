#!/usr/bin/env python3
"""
Test: Can an AI (Gemini) discover all skill .md files from the AirSkill index?

Flow:
1. Build expected set of Direct Links from filesystem (skills/**/*.md).
2. Give Gemini the root index content + group index content(s).
3. Ask Gemini to list every Direct Link it would fetch to get all skills.
4. Parse Gemini response and compare to expected.
"""

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
        sys.exit("Install: pip install google-generativeai")

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


def main() -> int:
    expected = get_expected_urls()
    index_text = get_index_text()
    group_texts = get_group_index_texts()

    print("Expected URLs (from filesystem):", len(expected))

    # 1) Programmatic parse (no API): index + group index must contain all expected
    parsed = parse_index_programmatically(index_text, group_texts)
    missing_in_manifest = expected - parsed
    if missing_in_manifest:
        print("FAIL (manifest): Index content does not list these URLs:", file=sys.stderr)
        for u in sorted(missing_in_manifest):
            print("  ", u, file=sys.stderr)
        return 1
    print("PASS (manifest): All expected URLs appear in index / group index content.")

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("Set GEMINI_API_KEY to run Gemini discovery test (optional).")
        return 0

    try:
        response_text = run_gemini(api_key, index_text, group_texts)
    except Exception as e:
        print("Gemini error:", e, file=sys.stderr)
        return 1

    found = parse_urls_from_response(response_text)
    print("URLs Gemini reported:", len(found))

    missing = expected - found
    extra = found - expected

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


if __name__ == "__main__":
    sys.exit(main())
