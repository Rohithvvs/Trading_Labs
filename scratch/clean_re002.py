from pathlib import Path
import re

raw = Path(r"D:\Trading_Labs\Trading_Labs\scratch\re002_package.md").read_text(encoding="utf-8")
# unescape markdown escapes from google docs export style
text = raw
# convert \* to *, \# to #, \- to -, etc carefully
text = text.replace("\\*\\*", "§BOLD§")
text = text.replace("\\*", "*")
text = text.replace("§BOLD§", "**")
text = text.replace("\\#", "#")
text = text.replace("\\-", "-")
text = text.replace("\\.", ".")
text = text.replace("\\>", ">")
text = text.replace("\\|", "|")
text = text.replace("\\[", "[")
text = text.replace("\\]", "]")
text = text.replace("\\(", "(")
text = text.replace("\\)", ")")

out = Path(r"D:\Trading_Labs\Trading_Labs\scratch\re002_clean.md")
out.write_text(text, encoding="utf-8")
print("clean len", len(text))

# Split by documents
for label, start_pat, end_pat in [
    ("01", r"# \*\*RE-002 – Document 01\*\*", r"# \*\*RE-002 – Document 02\*\*"),
    ("02", r"# \*\*RE-002 – Document 02\*\*", r"# \*\*RE-002 – Document 03\*\*"),
    ("03", r"# \*\*RE-002 – Document 03\*\*", r"# \*\*RE-002 – Document 04\*\*"),
    ("04", r"# \*\*RE-002 – Document 04\*\*", r"# \*\*RE-002 – Document 05\*\*"),
]:
    m1 = re.search(start_pat, text)
    if not m1:
        # try without bold
        m1 = re.search(start_pat.replace(r"\*\*", ""), text)
    if not m1:
        print(label, "START NOT FOUND")
        continue
    m2 = re.search(end_pat, text[m1.end():])
    if m2:
        body = text[m1.start(): m1.end()+m2.start()]
    else:
        # take rest if last
        body = text[m1.start():]
    Path(rf"D:\Trading_Labs\Trading_Labs\scratch\re002_doc{label}.md").write_text(body, encoding="utf-8")
    print(label, "len", len(body), "head:", body[:80].replace("\n"," "))

# print section headers for each doc
for i in ["01","02","03","04"]:
    p = Path(rf"D:\Trading_Labs\Trading_Labs\scratch\re002_doc{i}.md")
    if not p.exists():
        continue
    t = p.read_text(encoding="utf-8")
    print(f"\n==== DOC {i} HEADERS ====")
    for line in t.splitlines():
        if line.startswith("#") or line.startswith("##"):
            print(line[:120])
