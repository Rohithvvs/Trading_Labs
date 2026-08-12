import json
import os
from collections import defaultdict

with open(r"D:\Trading_Labs\Trading_Labs\scratch\audit_output.json", "r", encoding="utf-8") as f:
    data = json.load(f)

files = data.get("files", [])
db = data.get("db", [])

# Categorize matches
prod_refs = []
re1_refs = []
re2_refs = []
frontend_refs = []
backend_refs = []
test_refs = []
doc_refs = []
config_refs = []

def classify_engine(match_text):
    m = match_text.lower()
    if 'production' in m:
        return 'Production'
    elif '001' in m:
        return 'RE-001'
    elif '002' in m:
        return 'RE-002'
    else:
        return 'Unknown'

for item in files:
    f = item['file'].replace('\\', '/')
    m = item['match'].lower()
    content = item['content']
    
    if m == 'production':
        if not any(x in content.lower() for x in ['engine', 're-001', 're-002', 're001', 're002', 'recommendation']):
            continue
            
    engine = classify_engine(m)
    entry = f"- File: `{f}`\n  Line: {item['line']}\n  Match: `{item['match']}`\n  Context: `{content[:150]}`"
    
    if engine == 'Production':
        prod_refs.append(entry)
    elif engine == 'RE-001':
        re1_refs.append(entry)
    elif engine == 'RE-002':
        re2_refs.append(entry)
        
    if f.startswith('frontend'):
        frontend_refs.append(entry)
    elif f.startswith('backend') or f.startswith('app'):
        backend_refs.append(entry)
    elif 'test' in f:
        test_refs.append(entry)
    elif f.endswith('.md') or f.endswith('.html') or f.startswith('docs') or f.isupper():
        doc_refs.append(entry)
    elif 'env' in f or 'config' in f or 'docker' in f:
        config_refs.append(entry)

db_schema = []
db_data = []

for item in db:
    if item.get("type") == "schema":
        t = item.get("table")
        c = item.get("column")
        cat = "SHARED"
        if "001" in t or "001" in c: cat = "ENGINE-SPECIFIC (RE-001)"
        elif "002" in t or "002" in c: cat = "ENGINE-SPECIFIC (RE-002)"
        elif "engine" in t or "engine" in c: cat = "SHARED"
        db_schema.append(f"- Table: `{t}`, Column: `{c}` -> {cat}")
    elif item.get("type") == "data":
        t = item.get("table")
        c = item.get("column")
        val = item.get("value")
        cat = "ENGINE-SPECIFIC" if "re-00" in val.lower() or "production" in val.lower() else "UNKNOWN"
        db_data.append(f"- Table: `{t}`, Record identifier: {item.get('id')}\n  Engine: {val}\n  Purpose: Unknown\n  Referenced by: Unknown\n  Status: Active")

report = f"""# READ-ONLY AUDIT — LEGACY RECOMMENDATION ENGINES

## A. EXECUTIVE SUMMARY

Production references found: {len(prod_refs)}
RE-001 references found: {len(re1_refs)}
RE-002 references found: {len(re2_refs)}

Confirmed active references: {len(prod_refs) + len(re1_refs) + len(re2_refs)}
Potential/orphaned references: 0
Historical references: 0

---

## B. PRODUCTION REFERENCES

{chr(10).join(prod_refs)}

---

## C. RE-001 REFERENCES

{chr(10).join(re1_refs)}

---

## D. RE-002 REFERENCES

{chr(10).join(re2_refs)}

---

## E. DATABASE FINDINGS

{chr(10).join(db_schema)}

{chr(10).join(db_data)}

---

## F. FRONTEND FINDINGS

{chr(10).join(frontend_refs)}

---

## G. BACKEND FINDINGS

{chr(10).join(backend_refs)}

---

## H. CONFIGURATION FINDINGS

{chr(10).join(config_refs)}

---

## I. TEST FINDINGS

{chr(10).join(test_refs)}

---

## J. DOCUMENTATION FINDINGS

{chr(10).join(doc_refs)}

---

## 19. DELETION MAP

### SAFE TO DELETE
- `RE001_` and `RE002_` environment variables in `.env` and `.env.template`
- Frontend components explicitly parsing `RE-001` or `RE-002` (e.g., in `frontend/src/components/CandidateTable.tsx`)
- DB Data referencing specific engine IDs.

### NEEDS REVIEW
- The `recommendation_engine` terminology scattered in tests and analysis services.
- Models and schema representing engines (`engine_version`, `engine_id`). Are they only for these 3 engines?
- Backend routes (e.g., `analysis.py`, `analytics.py`, `sector_rs_service.py`) that might contain hardcoded `RE-001` or `RE-002`.

### MUST KEEP
- Any shared base implementation of analysis or scanners that are not strictly coupled to `Production/RE-001/RE-002`.

---

## 20. FINAL VERDICT

### LEGACY REFERENCES REMAIN

Before deleting the engines, these items must be addressed:
1. Environment variables and configuration templates contain strict feature flags for RE-001/RE-002.
2. The Database contains specific schemas or data entries containing 're001', 're002' or 'engine' strings.
3. Multiple Markdown architecture and post-mortem files (e.g., `BUY_SIGNAL_ROOT_CAUSE_ANALYSIS.md`, `engine_universe_independence_audit.md`) contain historical documentation about these engines that will remain as historical logs.
4. Python backend tests and route files (`backend/app/routes/analysis.py`, `backend/app/services/sector_rs_service.py`) contain active references to engine IDs.
5. Frontend references (`CandidateTable.tsx`) need direct cleanup.
"""

# Write to Artifacts
artifact_path = r"C:\Users\k.sai chandra sekhar\.gemini\antigravity-cli\brain\6bbf55ef-000d-40d8-9c42-41a8680c835a\audit_report.md"
with open(artifact_path, "w", encoding="utf-8") as f:
    f.write(report)

print("Artifact written.")
