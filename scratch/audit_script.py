import os
import re
import json

root_dir = r"D:\Trading_Labs\Trading_Labs"

exclude_dirs = {'.git', 'node_modules', '__pycache__', 'venv', '.venv', 'env', '.pytest_cache', 'build', 'dist', '.agents'}
exclude_exts = {'.pyc', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.pdf', '.zip', '.tar', '.gz', '.db', '.sqlite3', '.log'}

terms_patterns = {
    'Production': r'\bProduction\b',
    'RE-001': r'RE-001',
    'RE-002': r'RE-002',
    're001': r're001',
    're002': r're002',
    'production_engine': r'production_engine',
    'recommendation_engine': r'recommendation_engine',
    'RecommendationEngine': r'RecommendationEngine',
    'Recommendation Engine': r'Recommendation Engine',
    'recommendation-engine': r'recommendation-engine',
    'Recommendation Lab': r'Recommendation Lab',
    'recommendation-lab': r'recommendation-lab',
    'Rec Lab': r'Rec Lab',
    'engine registry': r'engine registry',
    'engine registration': r'engine registration',
    'engine config': r'engine config',
    'engine factory': r'engine factory',
    'engine loader': r'engine loader',
    'engine result': r'engine result',
    'engine decision': r'engine decision',
    'engine statistics': r'engine statistics',
    'engine comparison': r'engine comparison',
    'engine performance': r'engine performance',
    'engine attribution': r'engine attribution',
    'engine strategy': r'engine strategy',
    'engine_id': r'engine_id',
    'engine_name': r'engine_name',
    'engine_type': r'engine_type',
    'engine_key': r'engine_key',
    'engine_slug': r'engine_slug',
    'engine_version': r'engine_version',
    'engine_code': r'engine_code',
    'engine_registry': r'engine_registry',
    'engine_config': r'engine_config',
    'engine_result': r'engine_result',
    'engine_decision': r'engine_decision',
    'engine_stats': r'engine_stats',
    'engine_attribution': r'engine_attribution',
    'lab_id': r'lab_id',
    'lab_engine': r'lab_engine',
    'experiment_id': r'experiment_id',
    'strategy_id': r'strategy_id'
}

combined_pattern = re.compile(
    r"(" + "|".join(terms_patterns.values()) + r")", re.IGNORECASE
)

findings = []

for dirpath, dirnames, filenames in os.walk(root_dir):
    dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
    for file in filenames:
        ext = os.path.splitext(file)[1].lower()
        if ext in exclude_exts or file.endswith('.jsonl'):
            continue
        filepath = os.path.join(dirpath, file)
        rel_path = os.path.relpath(filepath, root_dir)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line_no, line in enumerate(f, 1):
                    if len(line) > 1000:  # Skip super long lines
                        continue
                    matches = combined_pattern.finditer(line)
                    found = set(m.group(1).lower() for m in matches)
                    if found:
                        for match in found:
                            findings.append({
                                "file": rel_path,
                                "line": line_no,
                                "match": match,
                                "content": line.strip()[:200]
                            })
        except Exception:
            pass

# Now Database
db_findings = []
try:
    import psycopg2
    from psycopg2 import sql
    # Use env var or hardcoded for test
    # DATABASE_URL =postgresql://neondb_owner:npg_XB9ITPDZ1Vbj@ep-old-dew-axui6i8s-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require
    conn = psycopg2.connect("postgresql://neondb_owner:npg_XB9ITPDZ1Vbj@ep-old-dew-axui6i8s-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require")
    cur = conn.cursor()
    
    # Tables and Columns
    cur.execute("""
        SELECT table_name, column_name 
        FROM information_schema.columns 
        WHERE table_schema = 'public'
    """)
    for table_name, column_name in cur.fetchall():
        if combined_pattern.search(table_name) or combined_pattern.search(column_name):
            db_findings.append({
                "type": "schema",
                "table": table_name,
                "column": column_name
            })
            
    # Search data in text/varchar columns of relevant tables? 
    # That might be slow. Let's just check specific likely tables for now if we can't search all.
    # We will search all text/varchar columns in public schema
    cur.execute("""
        SELECT table_name, column_name 
        FROM information_schema.columns 
        WHERE table_schema = 'public' AND data_type IN ('character varying', 'text')
    """)
    cols = cur.fetchall()
    
    for table_name, column_name in cols:
        query = sql.SQL("SELECT id, {col} FROM {table} WHERE {col} ILIKE '%Production%' OR {col} ILIKE '%RE-001%' OR {col} ILIKE '%RE-002%' OR {col} ILIKE '%re001%' OR {col} ILIKE '%re002%' LIMIT 100").format(
            col=sql.Identifier(column_name),
            table=sql.Identifier(table_name)
        )
        try:
            cur.execute(query)
            rows = cur.fetchall()
            for r in rows:
                db_findings.append({
                    "type": "data",
                    "table": table_name,
                    "column": column_name,
                    "id": r[0],
                    "value": str(r[1])
                })
        except Exception:
            conn.rollback()
            continue
            
    cur.close()
    conn.close()
except Exception as e:
    db_findings.append({"error": str(e)})

with open(r"D:\Trading_Labs\Trading_Labs\scratch\audit_output.json", "w", encoding='utf-8') as f:
    json.dump({"files": findings, "db": db_findings}, f, indent=2)

print("Audit complete.")
