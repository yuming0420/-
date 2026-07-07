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

mcp = "MediaCrawler/data/douyin/jsonl/search_contents_2026-07-03.jsonl"
with open(mcp, "r", encoding="utf-8") as f:
    items = [json.loads(line) for line in f if line.strip()]

# Dedup by creator_hash
seen = {}
for item in items:
    h = item.get("creator_hash", "")
    if h and h not in seen:
        seen[h] = item
items = list(seen.values())

print(f"Processing {len(items)} unique creators with DeepSeek-V4-Pro...")
saved = 0
for item in items:
    enriched = agent.extract_from_profile(item)
    tags_val = enriched.get("tags", [])
    tags_str = ", ".join(tags_val) if isinstance(tags_val, list) else str(tags_val)
    
    lead = {
        "platform": "dy",
        "user_id": item.get("creator_hash", ""),
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
    saved += 1
    if saved % 5 == 0 or saved == len(items):
        print(f"  [{saved}/{len(items)}] OEM={enriched.get('oem_score',0):.0f} | {enriched.get('category','?')} | {lead['nickname']}")

print(f"\nDone: {saved} leads")
s = get_stats()
print(f"DB total: {s['total']}")

# Auto export
leads = get_conn().execute("SELECT * FROM leads ORDER BY oem_score DESC LIMIT 50").fetchall()
leads = [dict(r) for r in leads]
path = exp.export(leads, fmt="xlsx")
print(f"Exported to: {path}")
