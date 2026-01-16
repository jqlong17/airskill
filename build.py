#!/usr/bin/env python3
import glob
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SKILLS_DIR = ROOT / "skills"
TEMPLATE_PATH = ROOT / "templates" / "manifest_template.txt"
OUTPUT_PATH = ROOT / "index.html"
CNAME_PATH = ROOT / "CNAME"


def extract_summary(content: str) -> str:
    lines = [line.strip() for line in content.splitlines()]
    after_header = False
    for line in lines:
        if not line:
            continue
        if line.lower().startswith("system prompt"):
            after_header = True
            continue
        if after_header:
            return line.replace("|", " / ")
    return ""


def build_skill_list() -> str:
    skill_files = sorted(glob.glob(str(SKILLS_DIR / "*.md")))
    rows = []
    for path in skill_files:
        filename = os.path.basename(path)
        skill_id = os.path.splitext(filename)[0]
        link = f"https://skill.ruska.cn/skills/{filename}"
        content = Path(path).read_text(encoding="utf-8")
        summary = extract_summary(content)
        rows.append(f"| {skill_id} | {link} | {summary} |")
    return "\n".join(rows)


def main() -> None:
    CNAME_PATH.write_text("skill.ruska.cn\n", encoding="utf-8")

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    skill_list = build_skill_list()
    manifest = template.replace("{{SKILL_LIST}}", skill_list)

    html = "<pre>\n" + manifest + "\n</pre>\n"
    OUTPUT_PATH.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
