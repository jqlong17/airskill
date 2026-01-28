# AirSkill tests

## test_airskill_discovery.py

Checks that an AI can discover all skill `.md` files from the AirSkill index.

1. **Manifest check (no API)**  
   Parses `index.html` and each group `index.md` and verifies every `skills/**/*.md` URL appears. Run:
   ```bash
   python3 tests/test_airskill_discovery.py
   ```

2. **Gemini check (optional)**  
   Uses Google Gemini to simulate an AI reading the manifest and listing every Direct Link; then compares to the filesystem. The API call may take 30–60s. Requires:
   ```bash
   pip install -r tests/requirements.txt
   export GEMINI_API_KEY=your_gemini_api_key
   python3 tests/test_airskill_discovery.py
   ```
   Do not commit API keys; use env or a local `.env` that is gitignored.

3. **Result file**  
   Every run writes:
   - **tests/output/discovery_result.md** — 技能评估表（每行一个技能）及汇总。列：skill、skill的描述、AI是否能理解、为什么说能理解和调用、skill描述有效性的评分（1–5）；文末为 Root index / Group row summaries / Per-group index / Gemini 的 PASS/FAIL 汇总。
   - **tests/output/discovery_result.csv** — 同上表格的 CSV 版本，便于导入或二次分析。
