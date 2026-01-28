#!/usr/bin/env python3
"""
从本地 GitHub 仓库做「反向工程 / 深度提炼」：提取该项目体现的可复用专业知识（架构模式、设计决策、领域概念、最佳实践），
写成 3～5 个可共享的 skill，写入 skills/<group>/ 并发布到公开索引。目标不是写产品使用手册，而是让 AI/开发者能复用这些知识。

用法:
  python3 scripts/ingest_repo.py /path/to/local/repo [--group GROUP]
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills"
BUILD_PY = ROOT / "build.py"

# Load .env from project root
_env = ROOT / ".env"
if _env.is_file():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env)
    except ImportError:
        pass


def sanitize_slug(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^\w\-]", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "skill"


SKIP_DIRS = {"node_modules", "vendor", ".git", "__pycache__", "dist", "build", "coverage", ".next", ".nuxt"}
MAX_README = 14000
MAX_DOC = 8000
MAX_SOURCE_LINES = 120
MAX_SOURCE_FILES = 12


def _read_head(path: Path, max_chars: int = 0, max_lines: int = 300) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        head = "\n".join(lines[:max_lines])
        if max_chars > 0 and len(head) > max_chars:
            head = head[:max_chars] + "\n...(truncated)"
        return head
    except Exception:
        return ""


def gather_repo_context(repo_path: Path) -> str:
    """收集仓库的 README、文档、目录结构、关键源码片段，供「反向工程」提炼可复用技能。"""
    repo_path = repo_path.resolve()
    if not repo_path.is_dir():
        raise SystemExit(f"不是目录: {repo_path}")

    lines = [f"# 仓库: {repo_path.name}", ""]

    # README
    for name in ("README.md", "README.MD", "readme.md", "README.rst"):
        p = repo_path / name
        if p.is_file():
            lines.append("## README")
            lines.append(_read_head(p, max_chars=MAX_README, max_lines=500))
            lines.append("")
            break

    # 架构/设计类文档（若有）
    for name in ("ARCHITECTURE.md", "DESIGN.md", "CONTRIBUTING.md", "docs/README.md", "doc/README.md"):
        p = repo_path / name
        if p.is_file():
            lines.append(f"## {name}")
            lines.append(_read_head(p, max_chars=MAX_DOC, max_lines=300))
            lines.append("")
    for d in ("docs", "doc"):
        doc_dir = repo_path / d
        if doc_dir.is_dir():
            for f in sorted(doc_dir.glob("*.md"))[:5]:
                lines.append(f"## {d}/{f.name}")
                lines.append(_read_head(f, max_chars=MAX_DOC, max_lines=200))
                lines.append("")

    # 顶层结构
    try:
        entries = sorted(repo_path.iterdir())
        top_files = [e.name for e in entries if e.is_file()][:25]
        top_dirs = [e.name for e in entries if e.is_dir() and not e.name.startswith(".") and e.name not in SKIP_DIRS][:15]
        lines.append("## 顶层结构")
        lines.append("文件: " + ", ".join(top_files) if top_files else "(无)")
        lines.append("目录: " + ", ".join(top_dirs) if top_dirs else "(无)")
        lines.append("")
    except Exception:
        pass

    # 关键配置/入口（用于理解技术栈与入口）
    for name in ("package.json", "pyproject.toml", "Cargo.toml", "tsconfig.json"):
        p = repo_path / name
        if p.is_file():
            lines.append(f"## 配置/入口: {name}")
            lines.append(_read_head(p, max_lines=80))
            lines.append("")

    # 源码抽样：从 src / lib / packages / 核心目录取若干文件前 N 行，用于推断架构与模式
    sampled = 0
    for dir_name in ("src", "lib", "packages", "core", "server", "app"):
        dir_path = repo_path / dir_name
        if not dir_path.is_dir() or sampled >= MAX_SOURCE_FILES:
            continue
        try:
            files = [f for f in dir_path.rglob("*") if f.is_file() and f.suffix in (".ts", ".js", ".py", ".go", ".rs", ".md") and not any(s in f.parts for s in SKIP_DIRS)][:20]
            for f in files[: MAX_SOURCE_FILES - sampled]:
                head = _read_head(f, max_lines=MAX_SOURCE_LINES)
                if len(head.strip()) < 30:
                    continue
                lines.append(f"## 源码片段: {f.relative_to(repo_path)}")
                lines.append(head)
                lines.append("")
                sampled += 1
                if sampled >= MAX_SOURCE_FILES:
                    break
        except Exception:
            pass

    return "\n".join(lines)


def call_llm(api_key: str, context: str, repo_name: str) -> str:
    try:
        import google.generativeai as genai
    except ImportError:
        raise SystemExit("需要安装: pip install google-generativeai")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")

    prompt = f"""你是一个「反向工程 / 深度提炼」专家。下面是一个 GitHub 仓库的摘要。请从中提炼出 **3～5 个独立的、可复用的专家级技能**，技能名与内容 **不得出现该仓库名、产品名或任何具体项目名**，只写 **领域级、可复用到任意项目** 的专家知识。

约束：
- 技能是「独立技能」：命名与描述均抽象为领域/模式（如 multi-agent-broadcast-design、message-envelope-normalization、streaming-llm-debugging），不绑定任何具体项目。
- 正文中不写「参考 XX 项目」「在 Clawdbot 中」等，只写通用原则、设计点、步骤、表格；可写「典型实现」「常见配置项」等中性表述。
- 内容深度参考 memory-system：多节、列表/表格/步骤，不要一两句话。

输出格式（必须严格遵循）：
1) 第一行：Group: <topic-slug>
   topic-slug 为**领域/主题**的英文短名（如 multi-agent-messaging、llm-observability），不是仓库名。
2) 空一行后，输出 3～5 个 ## Skill 块，结构如下：

## Skill 1: slug-here
System Prompt:
You are an expert on [领域]. Use this skill when [典型场景].

When to use this skill:
- [场景1]
- [场景2]

Core principles / Rules / Design points:
- [原则或规则1]
- [原则或规则2]

[可选：表格、步骤、示例]
[可选] If the user needs X, point them to 同组其他技能或通用文档。

## Skill 2: another-slug
System Prompt:
...（同样：多节、与参考格式相当长度，且不出现具体项目名。）
---
（slug 英文小写+连字符，领域级命名。）

仓库摘要（仅作分析用，不要在技能中引用其项目名）:

---
{context}
---
请直接输出：第一行 Group: <topic-slug>，然后空行，然后 3～5 个 ## Skill 块。不要其他解释。"""

    response = model.generate_content(prompt)
    if not response or not response.text:
        raise RuntimeError("LLM 返回为空")
    return response.text


def parse_group_and_skills(llm_output: str):
    # -> (group or None, [(slug, content), ...])
    """解析 LLM 输出：首行 Group: <topic-slug> 为组名（可选），其余为 ## Skill 块。返回 (group, [(slug, content), ...])。"""
    text = llm_output.strip()
    group = None
    if text.lower().startswith("group:"):
        first_line, rest = text.split("\n", 1)
        group = sanitize_slug(first_line.split(":", 1)[1].strip())
        text = rest.strip()

    skills = []
    pattern = re.compile(
        r"##\s*Skill\s*\d*\s*:\s*([^\n]+)\s*\n\s*System\s*Prompt\s*:\s*\n(.*?)(?=\n##\s*Skill|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    for m in pattern.finditer(text):
        slug = sanitize_slug(m.group(1))
        body = m.group(2).strip()
        body = re.sub(r"\n*```\s*\Z", "", body)
        if slug and body:
            skills.append((slug, f"System Prompt:\n{body}\n"))
    return (group, skills)


def main() -> None:
    ap = argparse.ArgumentParser(description="从本地仓库抽象 3-5 个 skill 并加入 AirSkill 索引")
    ap.add_argument("repo_path", type=Path, help="本地仓库目录路径")
    ap.add_argument("--group", "-g", default=None, help="技能组名（默认用仓库文件夹名）")
    args = ap.parse_args()

    repo_path = args.repo_path.resolve()
    if not repo_path.is_dir():
        raise SystemExit(f"目录不存在: {repo_path}")

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("请设置 GEMINI_API_KEY（或在本项目根目录 .env 中配置）")

    print("正在收集仓库上下文...")
    context = gather_repo_context(repo_path)
    print("正在调用 LLM 提炼技能（领域级、不绑定项目名）...")
    raw = call_llm(api_key, context, repo_path.name)
    llm_group, skills = parse_group_and_skills(raw)
    # 组名：用户 --group 优先，否则用 LLM 给出的领域组名，否则用仓库名
    if args.group:
        group = sanitize_slug(args.group)
    elif llm_group:
        group = llm_group
        print(f"使用 LLM 给出的领域组名: {group}")
    else:
        group = sanitize_slug(repo_path.name)
    if not group:
        group = "ingested"
    if not skills:
        print("未能解析出技能，请检查 LLM 输出格式。原始输出：", file=sys.stderr)
        print(raw[:2000], file=sys.stderr)
        raise SystemExit(1)

    print(f"解析到 {len(skills)} 个技能: {[s[0] for s in skills]}")
    out_dir = SKILLS_DIR / group
    out_dir.mkdir(parents=True, exist_ok=True)
    for slug, content in skills:
        (out_dir / f"{slug}.md").write_text(content, encoding="utf-8")
        print(f"  写入 {out_dir / f'{slug}.md'}")

    print("正在运行 build.py 更新索引...")
    subprocess.run([sys.executable, str(BUILD_PY)], check=True, cwd=str(ROOT))
    print("完成。新技能组:", group, "->", f"https://skill.ruska.cn/skills/{group}/index.md")


if __name__ == "__main__":
    main()
