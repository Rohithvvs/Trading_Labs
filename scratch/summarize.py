import json
from collections import defaultdict

with open(r"D:\Trading_Labs\Trading_Labs\scratch\audit_output.json", "r", encoding="utf-8") as f:
    data = json.load(f)

files = data.get("files", [])
db = data.get("db", [])

file_counts = defaultdict(lambda: defaultdict(int))
term_counts = defaultdict(int)

# Group by file and term
for item in files:
    file = item["file"]
    match = item["match"].lower()
    file_counts[file][match] += 1
    term_counts[match] += 1

print(f"Total file matches: {len(files)}")
print(f"Total DB matches: {len(db)}")
print("\nTop Terms:")
for term, count in sorted(term_counts.items(), key=lambda x: x[1], reverse=True):
    print(f"  {term}: {count}")

# Print unique DB findings
print("\nDB Schema Findings:")
for item in db:
    if item.get("type") == "schema":
        print(f"  Table: {item.get('table')}, Column: {item.get('column')}")
    elif item.get("error"):
        print(f"  DB Error: {item.get('error')}")

print("\nDB Data Findings (Samples):")
data_count = 0
for item in db:
    if item.get("type") == "data":
        data_count += 1
        if data_count <= 20:
            print(f"  Table: {item.get('table')}, Column: {item.get('column')}, ID: {item.get('id')}, Value: {item.get('value')[:50]}...")
print(f"Total DB Data Rows: {data_count}")

# Files with highest density of RE terms
print("\nFiles with RE terms (excluding generic 'production'):")
for file, counts in sorted(file_counts.items(), key=lambda x: sum(x[1].values()), reverse=True):
    # check if there is something other than 'production'
    non_prod = {k: v for k, v in counts.items() if k != 'production'}
    if non_prod:
        print(f"{file}: {dict(counts)}")

