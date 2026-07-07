# -*- coding: utf-8 -*-
"""任务编排入口 - 达人对接系统"""

import sys
import os
import argparse
import yaml
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv()

from storage.database import init_db, upsert_lead, search_leads, update_status, get_stats
from agent.extractor import AgentExtractor
from scraper.crawler import ScraperEngine
from export.exporter import Exporter


def load_config():
    with open(Path(__file__).parent / "config" / "settings.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def cmd_search(args, config):
    """搜索达人并入库"""
    scraper = ScraperEngine(config)
    agent = AgentExtractor(config)
    init_db(config["database"]["path"])

    print(f"\n{'='*50}")
    print(f"  搜索任务: 平台={args.platform}, 关键词={args.keyword}")
    print(f"{'='*50}\n")

    raw_leads = scraper.search_creators(args.platform, args.keyword, args.max or 30)
    if not raw_leads:
        print("[!] 未获取到数据")
        return

    # 读取评论区数据
    comments = scraper.get_comments(args.platform)
    comments_by_aweme = {}
    for c in comments:
        aweme_id = c["aweme_id"]
        comments_by_aweme.setdefault(aweme_id, []).append(c["content"])

    saved = 0
    for i, raw in enumerate(raw_leads):
        print(f"\n[{i+1}/{len(raw_leads)}] 处理 {raw['nickname']}...")

        # 合并评论到 raw 数据中
        aweme_id = raw["raw"].get("aweme_id", "")
        raw["raw"]["related_comments"] = comments_by_aweme.get(aweme_id, [])[:10]

        # Agent 智能提取
        enriched = agent.extract_from_profile(raw["raw"])

        tags_val = enriched.get("tags", [])
        tags_str = ", ".join(tags_val) if isinstance(tags_val, list) else str(tags_val)

        lead = {
            "platform": args.platform,
            "user_id": raw["user_id"],
            "nickname": raw["nickname"],
            "avatar_url": raw["raw"].get("avatar_url", ""),
            "homepage_url": raw["homepage_url"],
            "followers": raw["followers"],
            "avg_likes": raw["avg_likes"],
            "avg_comments": raw["avg_comments"],
            "bio": raw["bio"],
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
            "account_type": enriched.get("account_type"),
            "mcn_focus": enriched.get("mcn_focus"),
            "mcn_relevance": enriched.get("mcn_relevance", 0.0),
        }
        upsert_lead(lead)
        saved += 1
        print(f"    [OK] OEM={enriched.get('oem_score',0):.0f} | 分类={enriched.get('category','?')} | {enriched.get('contact_source','无联系方式')}")

    print(f"\n[OK] 完成: 入库 {saved} 条达人记录")

    # 显示统计
    stats = get_stats()
    print(f"    数据库总计: {stats['total']} 条")


def cmd_export(args, config):
    """导出达人名单"""
    init_db(config["database"]["path"])
    exp = Exporter(config)

    leads = search_leads(
        platform=args.platform or None,
        category=args.category or None,
        min_oem=args.min_oem or 0,
        min_followers=args.min_followers or 0,
        limit=args.limit or 500
    )

    if not leads:
        print("[!] 没有符合条件的数据")
        return

    path = exp.export(leads, fmt=args.format or None)
    print(f"\n[Export] 导出统计:")
    print(f"   总数: {len(leads)}")
    if leads:
        top3 = sorted(leads, key=lambda x: x.get("oem_score", 0), reverse=True)[:3]
        print(f"   TOP3 OEM达人: {', '.join(str(l.get('nickname','')) for l in top3)}")


def cmd_stats(args, config):
    """查看统计"""
    init_db(config["database"]["path"])
    s = get_stats()
    print(f"\n[Stats] 数据库统计")
    print(f"   总记录: {s['total']}")
    print(f"   按平台: {s['by_platform']}")
    print(f"   按赛道: {s['by_category']}")
    print(f"   按状态: {s['by_status']}")


def cmd_run_pipeline(args, config):
    """一键运行完整管线: 搜索 -> 提取 -> 导出"""
    print("\n" + "="*50)
    print("  一键管线: 搜索 -> Agent提取 -> 入库 -> 导出")
    print("="*50)

    init_db(config["database"]["path"])
    scraper = ScraperEngine(config)
    agent = AgentExtractor(config)
    exp = Exporter(config)

    raw_leads = scraper.search_creators(args.platform, args.keyword, args.max or 30)
    if not raw_leads:
        print("[!] 未获取到数据")
        return

    comments = scraper.get_comments(args.platform)
    comments_by_aweme = {}
    for c in comments:
        comments_by_aweme.setdefault(c["aweme_id"], []).append(c["content"])

    saved = 0
    for i, raw in enumerate(raw_leads):
        aweme_id = raw["raw"].get("aweme_id", "")
        raw["raw"]["related_comments"] = comments_by_aweme.get(aweme_id, [])[:10]
        enriched = agent.extract_from_profile(raw["raw"])

        tags_val = enriched.get("tags", [])
        tags_str = ", ".join(tags_val) if isinstance(tags_val, list) else str(tags_val)

        lead = {
            "platform": args.platform,
            "user_id": raw["user_id"],
            "nickname": raw["nickname"],
            "avatar_url": raw["raw"].get("avatar_url", ""),
            "homepage_url": raw["homepage_url"],
            "followers": raw["followers"],
            "avg_likes": raw["avg_likes"],
            "avg_comments": raw["avg_comments"],
            "bio": raw["bio"],
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
            "account_type": enriched.get("account_type"),
            "mcn_focus": enriched.get("mcn_focus"),
            "mcn_relevance": enriched.get("mcn_relevance", 0.0),
        }
        upsert_lead(lead)
        saved += 1
        print(f"  [{i+1}/{len(raw_leads)}] {raw['nickname']} | OEM={enriched.get('oem_score',0):.0f} | {enriched.get('category','?')}")

    print(f"\n[OK] 入库 {saved} 条")

    # 自动导出
    leads = search_leads(limit=500)
    if leads:
        path = exp.export(leads, fmt=args.format or "xlsx")
        print(f"[Export] 导出到 {path}")

    stats = get_stats()
    print(f"[Stats] 数据库总计: {stats['total']} 条")


def main():
    parser = argparse.ArgumentParser(description="达人对接系统 - 搜索达人、智能提取、导出名单")
    sub = parser.add_subparsers(dest="command")

    # search 子命令
    p_search = sub.add_parser("search", help="搜索达人并入库")
    p_search.add_argument("--platform", "-p", required=True, choices=["xhs", "dy", "ks", "bili", "weibo"])
    p_search.add_argument("--keyword", "-k", required=True, help="搜索关键词，如 健康食品")
    p_search.add_argument("--max", "-m", type=int, default=30, help="最大采集条数")

    # run 子命令: 一键管线
    p_run = sub.add_parser("run", help="一键管线: 搜索 -> 提取 -> 导出")
    p_run.add_argument("--platform", "-p", required=True, choices=["xhs", "dy", "ks", "bili", "weibo"])
    p_run.add_argument("--keyword", "-k", required=True, help="搜索关键词")
    p_run.add_argument("--max", "-m", type=int, default=30)
    p_run.add_argument("--format", "-f", choices=["xlsx", "csv"], default="xlsx")

    # export 子命令
    p_export = sub.add_parser("export", help="导出达人名单")
    p_export.add_argument("--platform", "-p", help="按平台筛选")
    p_export.add_argument("--category", "-c", help="按赛道筛选")
    p_export.add_argument("--min-oem", type=float, help="最低OEM评分")
    p_export.add_argument("--min-followers", type=int, help="最低粉丝数")
    p_export.add_argument("--format", "-f", choices=["xlsx", "csv"], help="导出格式")
    p_export.add_argument("--limit", "-l", type=int, default=500)

    # stats 子命令
    sub.add_parser("stats", help="查看数据库统计")

    args = parser.parse_args()
    config = load_config()

    if args.command == "search":
        cmd_search(args, config)
    elif args.command == "run":
        cmd_run_pipeline(args, config)
    elif args.command == "export":
        cmd_export(args, config)
    elif args.command == "stats":
        cmd_stats(args, config)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
