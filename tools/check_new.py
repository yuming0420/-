import json
with open("MediaCrawler/data/douyin/jsonl/search_contents_2026-07-03.jsonl", "r", encoding="utf-8") as f:
    lines = [l for l in f if l.strip()]
print(f"Total lines: {len(lines)}")
creators = set()
for line in lines:
    item = json.loads(line)
    creators.add(item.get("creator_hash",""))
print(f"Unique creators: {len(creators)}")
for line in lines[:3]:
    item = json.loads(line)
    desc = item.get("desc","")[:60]
    print(f"  {item.get('nickname','')} | {desc}")
