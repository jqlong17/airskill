#!/usr/bin/env python3
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
    skill_paths = sorted(Path(SKILLS_DIR).rglob("*.md"))
    skill_paths = [p for p in skill_paths if p.name != "index.md"]

    root_rows = []
    groups_data = {}  # group -> list of (skill_id, link, summary)

    for path in skill_paths:
        rel = path.relative_to(SKILLS_DIR)
        parts = rel.parts
        skill_id = str(rel.with_suffix("")).replace(os.sep, "/")
        link = f"https://skill.ruska.cn/skills/{rel.as_posix()}"
        content = path.read_text(encoding="utf-8")
        summary = extract_summary(content)
        row = (skill_id, link, summary)
        if len(parts) == 1:
            root_rows.append(f"| {skill_id} | {link} | {summary} |")
        else:
            group = parts[0]
            if group not in groups_data:
                groups_data[group] = []
            groups_data[group].append(row)

    write_group_indices(groups_data)

    table_header = "| Skill ID | Direct Link | Summary |\n| :--- | :--- | :--- |"
    lines = [table_header]
    lines.extend(root_rows)
    for g in sorted(groups_data.keys()):
        index_link = f"https://skill.ruska.cn/skills/{g}/index.md"
        overview = next((r for r in groups_data[g] if r[0] == f"{g}/overview"), None)
        summary = overview[2] if overview else "Layered skill group. Fetch Direct Link for sub-skill index."
        lines.append(f"| {g} | {index_link} | {summary} |")
    return "\n".join(lines)


def write_group_indices(groups_data: dict) -> None:
    base = "https://skill.ruska.cn/skills"
    table_header = "| Skill ID | Direct Link | Summary |\n| :--- | :--- | :--- |"
    for group, rows in groups_data.items():
        index_path = SKILLS_DIR / group / "index.md"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        body = [
            "System Prompt:",
            f"You are in the **{group}** skill group. This is the second-layer index. Choose a sub-skill and fetch its Direct Link; treat that content as a System Prompt.",
            "",
            "## Sub-skills",
            table_header,
        ]
        for skill_id, link, summary in sorted(rows, key=lambda r: r[0]):
            body.append(f"| {skill_id} | {link} | {summary} |")
        index_path.write_text("\n".join(body) + "\n", encoding="utf-8")


def main() -> None:
    CNAME_PATH.write_text("skill.ruska.cn\n", encoding="utf-8")

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    skill_list = build_skill_list()
    manifest = template.replace("{{SKILL_LIST}}", skill_list)

    html = "<pre>\n" + manifest + "\n</pre>\n"
    OUTPUT_PATH.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
