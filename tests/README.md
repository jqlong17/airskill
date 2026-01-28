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
