# AirSkill

面向 AI 的纯静态技能站点，部署在 [skill.ruska.cn](https://skill.ruska.cn)。无 UI，仅提供 Markdown 形式的技能清单与 System Prompt，供 AI 代理按需拉取使用。

---

## 项目是什么

首页是一份 Manifest，列出技能与分组；每个技能是一段 Markdown，可当作 System Prompt 使用。AI 打开首页 → 从 SKILL INDEX 选技能或分组 → 按 Direct Link 拉取对应 `.md` → 将内容视为 System Prompt 执行。

---

## 分层技能的核心思想

我们采用**分层索引**，而不是在首页堆出所有技能：

1. **主清单（index.html）只做「顶层」**
   - 单文件技能：如 `api-docs`、`prd-writer`、`python-expert` 等，一行一个，Direct Link 指向对应 `skills/xxx.md`。
   - 分组入口：如 `memory-system` 只占**一行**，Direct Link 指向 `skills/memory-system/index.md`，不在这里展开子技能。

2. **进入分组后再看「二层索引」**
   - 当 AI 需要某一类能力（例如记忆系统）时，先访问该组的 `index.md`，得到子技能列表，再按需拉取具体子技能。

3. **这样做的原因**
   - **主索引不臃肿**：首页只列「有哪些大类 / 单技能」，不把几十条子技能全塞在一页。
   - **结构清晰**：一个主题一组，组内再细分，AI 先选组、再选具体技能，两步完成。
   - **可扩展**：新增技能组时，在 `skills/` 下新建子目录并放 `.md` 即可，主清单与组内索引由构建脚本生成。

**目录约定**：`skills/` 下一级子目录为「组」，组内放多个 `.md`；根目录下的单文件 `skills/xxx.md` 为顶层单技能。

---

## 使用方式（AI）

1. 请求站点根 URL，获取首页 Manifest。
2. 从 SKILL INDEX 选技能或分组：单技能直接拉其 Direct Link；分组先拉该组的 `index.md`，再按子技能表拉取具体 `.md`。
3. 将拉取到的内容作为 System Prompt 使用。

---

## 从仓库摄入技能

输入任意本地 GitHub 仓库路径，脚本会扫描 README 与结构、用 LLM 提炼 3～5 个核心 skill，写入 `skills/<组名>/` 并更新索引。需配置 `GEMINI_API_KEY`。

```bash
python3 scripts/ingest_repo.py /path/to/local/repo [--group 组名]
```

---

## 构建与 Summary 生成

- **构建**：`python3 build.py` 会扫描 `skills/**/*.md`，生成主索引与各组 `index.md`。
- **单技能 / 组内子技能**：Summary 取自每个 `.md` 中「`System Prompt:` 下一行」的正文。
- **主索引里的「组」行**：若该组有 `overview.md`，用其 Summary；否则**必须**用 AI 生成：build 会读 `GEMINI_API_KEY`，用 Gemini 根据该组**全部子技能**的 Summary 生成一句概括（≤200 字）。若无 key、未安装 `google-generativeai` 或 API 失败，build 会**直接失败**并报错（无回退），需配置 key 或为该组添加 `overview.md`。
