import json
from pathlib import Path

p = Path(r"C:\Users\k.sai chandra sekhar\.grok\sessions\D%3A%5CTrading_Labs%5CTrading_Labs\019fcc33-97f0-75d3-bb23-25bcce3aa3bf\mcp\call-17ed0fbe-864e-488d-b859-b3316f22b439-28.json")
data = json.loads(p.read_text(encoding="utf-8"))

def find_content(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("content", "content_preview", "text", "body") and isinstance(v, str) and len(v) > 5000:
                return v
            r = find_content(v)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_content(v)
            if r:
                return r
    return None

content = find_content(data)
if not content:
    # maybe top-level is the whole thing as string somewhere
    s = json.dumps(data)
    # try extract "content": "..."
    key = '"content": "'
    i = s.find(key)
    print("content key at", i)
    raise SystemExit("no content")

out = Path(r"D:\Trading_Labs\Trading_Labs\scratch\all_res_drive.md")
out.write_text(content, encoding="utf-8")
print("saved full", len(content), "chars")

# split RE-002 section
markers = []
for term in ["# Re 2", "RE-002 Specification Package", "RE-002 – Document", "RE-002 - Document", "# **RE-002", "RE-002"]:
    idx = 0
    while True:
        j = content.find(term, idx)
        if j < 0:
            break
        markers.append((j, term, content[j:j+120].replace("\n"," ")))
        idx = j + len(term)
        if len(markers) > 40:
            break

print("markers count", len(markers))
for m in markers[:30]:
    print(m[0], m[1], "=>", m[2][:100])

# find RE-002 package start
start = content.find("RE-002 Specification Package")
if start < 0:
    start = content.find("# Re 2")
print("start", start)
re002 = content[start:] if start >= 0 else ""
Path(r"D:\Trading_Labs\Trading_Labs\scratch\re002_package.md").write_text(re002, encoding="utf-8")
print("re002 chars", len(re002))
print("---HEAD---")
print(re002[:3000])
