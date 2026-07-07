import sys
sys.path.insert(0, ".")
from dotenv import load_dotenv; load_dotenv()
from storage.database import init_db, get_conn
import yaml

with open("config/settings.yaml", encoding="utf-8") as f:
    config = yaml.safe_load(f)
init_db(config["database"]["path"])
conn = get_conn()

print("=== LLM提取成功的达人 (Top OEM) ===")
rows = conn.execute("""
    SELECT nickname, oem_score, category, oem_reason, intent_level
    FROM leads WHERE oem_score > 10
    ORDER BY oem_score DESC
""").fetchall()
for r in rows:
    print(f"  OEM={r['oem_score']:3.0f} | {r['category'] or '?':6s} | {r['nickname']}")
    print(f"         {r['oem_reason']}")

print()
print("=== 按赛道分布 ===")
rows = conn.execute("""
    SELECT category, COUNT(*) as cnt, ROUND(AVG(oem_score),0) as avg_oem
    FROM leads WHERE category IS NOT NULL
    GROUP BY category ORDER BY cnt DESC
""").fetchall()
for r in rows:
    print(f"  {r['category']}: {r['cnt']}人, 均分{r['avg_oem']:.0f}")

print()
rows = conn.execute("SELECT COUNT(*) as cnt FROM leads WHERE contact_source IS NOT NULL").fetchone()
print(f"有联系方式的达人: {rows['cnt']}")

conn.close()
