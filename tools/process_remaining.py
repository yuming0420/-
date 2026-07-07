import sys, json, yaml
sys.path.insert(0, ".")
from dotenv import load_dotenv; load_dotenv()
from storage.database import init_db, upsert_lead, get_stats, get_conn
from agent.extractor import AgentExtractor
from export.exporter import Exporter

with open("config/settings.yaml", encoding="utf-8") as f:
    config = yaml.safe_load(f)

init_db(config["database"]["path"])
agent = AgentExtractor(config)
exp = Exporter(config)

# Get already-processed creators from DB
conn = get_conn()
existing = {r["user_id"] for r in conn.execute("SELECT user_id FROM leads WHERE oem_score > 10").fetchall()}
conn.close()

mcp = "MediaCrawler/data/douyin/jsonl/search_contents_2026-07-03.jsonl"
with open(mcp, "r", encoding="utf-8") as f:
    items = [json.loads(line) for line in f if line.strip()]

seen = {}
for item in items:
    h = item.get("creator_hash", "")
    if h and h not in seen:
        seen[h] = item
items = list(seen.values())

# Filter unprocessed
new_items = [it for it in items if it.get("creator_hash","") not in existing]
print(f"Total unique creators: {len(items)}, already processed: {len(items)-len(new_items)}, remaining: {len(new_items)}")

if not new_items:
    print("All done!")
else:
    print(f"Processing {len(new_items)} remaining with DeepSeek-V4-Pro...")
    for i, item in enumerate(new_items):
        enriched = agent.extract_from_profile(item)
        tags_val = enriched.get("tags", [])
        tags_str = ", ".join(tags_val) if isinstance(tags_val, list) else str(tags_val)
        lead = {
            "platform": "dy", "user_id": item.get("creator_hash", ""),
            "nickname": item.get("nickname", ""),
            "avatar_url": item.get("cover_url", ""),
            "homepage_url": item.get("aweme_url", ""),
            "followers": 0,
            "avg_likes": int(item.get("liked_count", 0)),
            "avg_comments": int(item.get("comment_count", 0)),
            "bio": item.get("desc", ""),
            "email": enriched.get("email"),
            "wechat": enriched.get("wechat"),
            "phone": enriched.get("phone"),
            "contact_source": enriched.get("contact_source"),
            "category": enriched.get("category"),
            "tags": tags_str,
            "oem_score": enriched.get("oem_score", 0.0),
            "oem_reason": enriched.get("oem_reason", ""),
            "intent_signal": enriched.get("intent_signal"),
            "intent_level": enriched.get("intent_level"),
        }
        upsert_lead(lead)
        if (i+1) % 3 == 0 or i == len(new_items)-1:
            print(f"  [{i+1}/{len(new_items)}] OEM={enriched.get('oem_score',0):.0f} | {enriched.get('category','?')} | {lead['nickname']}")

    print(f"\nDone!")
    s = get_stats()
    print(f"DB total: {s['total']}")

# Export
leads = [dict(r) for r in get_conn().execute("SELECT * FROM leads ORDER BY oem_score DESC LIMIT 50").fetchall()]
path = exp.export(leads, fmt="xlsx")
print(f"Exported: {path}")
