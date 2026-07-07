import sys, yaml
sys.path.insert(0, ".")
from dotenv import load_dotenv; load_dotenv()
from storage.database import init_db, get_conn
with open("config/settings.yaml", encoding="utf-8") as f:
    config = yaml.safe_load(f)
init_db(config["database"]["path"])
conn = get_conn()
r1 = conn.execute("SELECT COUNT(*) as cnt FROM leads").fetchone()
r2 = conn.execute("SELECT COUNT(*) as cnt FROM leads WHERE oem_score > 10").fetchone()
print(f"Total: {r1['cnt']}, LLM-processed: {r2['cnt']}")
rows = conn.execute("SELECT nickname, oem_score, category, created_at FROM leads ORDER BY created_at DESC LIMIT 10").fetchall()
for r in rows:
    print(f"  OEM={r['oem_score']:3.0f} | {(r['category'] or '?'):10s} | {r['nickname']} | {r['created_at']}")
conn.close()
