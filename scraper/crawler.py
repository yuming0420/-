# -*- coding: utf-8 -*-
"""采集层 - MediaCrawler 封装（读取 JSONL 输出 + 子进程调用）"""

import subprocess
import sys
import os
import json
import time
import random
import yaml
import glob
from pathlib import Path
from typing import Optional
from datetime import datetime


class ScraperEngine:
    """MediaCrawler 采集引擎封装"""

    def __init__(self, config: dict):
        cfg = config.get("scraper", {})
        self.root = Path(cfg.get("media_crawler_path", "./MediaCrawler")).resolve()
        self.platforms = cfg.get("platforms", ["dy", "xhs", "ks", "bili", "weibo"])
        self.search_cfg = cfg.get("search", {})
        self.req_cfg = cfg.get("request", {})
        self._validate()

    def _validate(self):
        if not self.root.exists():
            raise FileNotFoundError(f"MediaCrawler 目录不存在: {self.root}")

    def _find_latest_jsonl(self, platform: str, content_type: str) -> Optional[Path]:
        """找到最新的 JSONL 数据文件"""
        # CLI 平台代码 → MediaCrawler 数据目录名映射
        _PLATFORM_DIR = {"dy": "douyin", "xhs": "xhs", "ks": "kuaishou", "bili": "bilibili", "wb": "weibo", "weibo": "weibo"}
        dir_name = _PLATFORM_DIR.get(platform, platform)
        pattern = str(self.root / "data" / dir_name / "jsonl" / f"{content_type}_*.jsonl")
        files = sorted(glob.glob(pattern), reverse=True)
        return Path(files[0]) if files else None

    def _run_media_crawler(self, platform: str, crawler_type: str, keywords: str, max_notes: int = 30):
        """调用 MediaCrawler 子进程采集数据"""
        cmd = [
            sys.executable, str(self.root / "main.py"),
            "--platform", platform,
            "--type", crawler_type,
            "--keywords", keywords,
            "--crawler_max_notes_count", str(max_notes),
            "--headless", "true",
        ]
        env = os.environ.copy()
        env.pop("HTTP_PROXY", None)
        env.pop("HTTPS_PROXY", None)
        env.pop("ALL_PROXY", None)
        env["PYTHONIOENCODING"] = "utf-8"

        print(f"[Scraper] 启动 MediaCrawler: {' '.join(cmd)}")
        result = subprocess.run(cmd, cwd=str(self.root), env=env,
                                capture_output=True, text=True, encoding='utf-8',
                                errors='replace', timeout=600)

        if result.returncode != 0:
            # Print last 20 lines of output for debugging
            stderr = result.stderr or ''; stderr_lines = stderr.strip().split("\n")[-20:]
            print("[Scraper] MediaCrawler 错误输出:")
            for line in stderr_lines:
                print(f"  {line}")
            raise RuntimeError(f"MediaCrawler 返回码 {result.returncode}")

        return result.stdout

    def search_creators(self, platform: str, keyword: str, max_results: int = 30) -> list[dict]:
        """搜索达人内容 → 返回结构化数据列表"""
        if platform not in self.platforms:
            raise ValueError(f"不支持的平台: {platform}，可用: {self.platforms}")

        # 1. 运行 MediaCrawler 搜索
        print(f"\n[Scraper] 搜索平台={platform} 关键词={keyword} 条数={max_results}")
        self._run_media_crawler(platform, "search", keyword, max_results)

        # 2. 读取最新的 JSONL 输出
        content_file = self._find_latest_jsonl(platform, "search_contents")
        if not content_file:
            return []

        leads = []
        with open(content_file, "r", encoding="utf-8") as f:
            for line in f:
                item = json.loads(line.strip())
                leads.append({
                    "platform": platform,
                    "user_id": item.get("creator_uid", ""),
                    "nickname": item.get("nickname", ""),
                    "bio": item.get("signature", ""),
                    "homepage_url": f"https://www.douyin.com/user/{item.get('creator_sec_uid', '')}" if item.get("creator_sec_uid") else item.get("aweme_url", ""),
                    "followers": int(item.get("follower_count", 0)),
                    "avg_likes": int(item.get("liked_count", 0)),
                    "avg_comments": int(item.get("comment_count", 0)),
                    "raw": item,
                })

        print(f"[Scraper] 读取到 {len(leads)} 条内容数据")
        return leads

    def get_creator_profile(self, platform: str, user_id: str) -> Optional[dict]:
        """获取达人主页详情（需先知道 sec_uid）"""
        print(f"[Scraper] 获取达人主页 {platform}/{user_id}")
        # TODO: 需要先用 creator 模式采集，这里暂时返回 None
        return None

    def get_comments(self, platform: str) -> list[dict]:
        """读取最新评论数据"""
        comment_file = self._find_latest_jsonl(platform, "search_comments")
        if not comment_file:
            return []

        comments = []
        with open(comment_file, "r", encoding="utf-8") as f:
            for line in f:
                item = json.loads(line.strip())
                comments.append({
                    "aweme_id": item.get("aweme_id", ""),
                    "content": item.get("content", ""),
                    "nickname": item.get("nickname", ""),
                    "like_count": int(item.get("like_count", 0)),
                    "create_time": item.get("create_time", ""),
                })

        return comments
