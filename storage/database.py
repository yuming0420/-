# -*- coding: utf-8 -*-
"""存储层 - SQLite 数据库操作"""

import sqlite3
import os
from datetime import datetime
from typing import Optional


DB_PATH: str = ""


def init_db(db_path: str):
    """初始化数据库，创建 leads 表"""
    global DB_PATH
    DB_PATH = db_path
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS leads (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            -- 基本身份
            platform        TEXT    NOT NULL,       -- xhs / dy / ks / bili / weibo
            user_id         TEXT    NOT NULL,       -- 平台用户ID
            nickname        TEXT,                   -- 昵称
            avatar_url      TEXT,                   -- 头像
            homepage_url    TEXT,                   -- 主页链接
            -- 达人数据
            followers       INTEGER DEFAULT 0,      -- 粉丝数
            avg_likes       INTEGER DEFAULT 0,      -- 平均点赞
            avg_comments    INTEGER DEFAULT 0,      -- 平均评论
            verified        INTEGER DEFAULT 0,      -- 是否认证
            -- 联系方式 (Agent提取)
            email           TEXT,
            wechat          TEXT,
            phone           TEXT,                   -- 通常需手动补充
            contact_source  TEXT,                   -- 联系方式来源: bio / comment / manual
            -- 标签 & 分类 (Agent提取)
            bio             TEXT,                   -- 个人简介原文
            category        TEXT,                   -- 赛道分类
            tags            TEXT,                   -- JSON数组: 内容标签
            -- OEM 评分 (Agent评估)
            oem_score       REAL    DEFAULT 0.0,    -- OEM潜力评分 0-100
            oem_reason      TEXT,                   -- 评分理由
            -- MCN/机构分析 (Agent评估)
            account_type    TEXT,                   -- 账号类型: creator / mcn
            mcn_focus       TEXT,                   -- MCN主攻赛道（仅MCN账号）
            mcn_relevance   REAL    DEFAULT 0.0,    -- MCN与大健康OEM匹配度 0-100
            -- 互动意向 (Agent识别)
            intent_signal   TEXT,                   -- 合作意向信号
            intent_level    TEXT,                   -- 意向等级: high / medium / low
            -- 跟进状态
            status          TEXT    DEFAULT 'new',  -- new / contacted / negotiating / cooperation / closed
            notes           TEXT,                   -- 人工备注
            -- 时间戳
            created_at      TEXT    DEFAULT (datetime('now','localtime')),
            updated_at      TEXT    DEFAULT (datetime('now','localtime')),
            UNIQUE(platform, user_id)
        );

        CREATE INDEX IF NOT EXISTS idx_platform ON leads(platform);
        CREATE INDEX IF NOT EXISTS idx_category ON leads(category);
        CREATE INDEX IF NOT EXISTS idx_oem_score ON leads(oem_score DESC);
        CREATE INDEX IF NOT EXISTS idx_status ON leads(status);
    """)
    conn.commit()
    # Migration: 添加后续新增的字段（忽略已存在的错误）
    migrations = [
        "ALTER TABLE leads ADD COLUMN account_type TEXT",
        "ALTER TABLE leads ADD COLUMN mcn_focus TEXT",
        "ALTER TABLE leads ADD COLUMN mcn_relevance REAL DEFAULT 0.0",
    ]
    for sql in migrations:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            pass  # 字段已存在
    conn.commit()
    conn.close()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def upsert_lead(lead: dict) -> int:
    """插入或更新 lead 记录"""
    conn = get_conn()
    lead["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    columns = list(lead.keys())
    values = [lead[c] for c in columns]
    placeholders = ", ".join(["?" for _ in columns])
    col_names = ", ".join(columns)
    updates = ", ".join([f"{c}=excluded.{c}" for c in columns if c not in ("platform", "user_id", "created_at")])
    sql = f"INSERT INTO leads ({col_names}) VALUES ({placeholders}) ON CONFLICT(platform, user_id) DO UPDATE SET {updates}"
    conn.execute(sql, values)
    conn.commit()
    row = conn.execute("SELECT id FROM leads WHERE platform=? AND user_id=?", (lead["platform"], lead["user_id"])).fetchone()
    conn.close()
    return row["id"] if row else -1


def search_leads(
    platform: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    min_oem: float = 0,
    min_followers: int = 0,
    limit: int = 100
) -> list[dict]:
    """多条件查询 leads"""
    conn = get_conn()
    conditions = []
    params = []
    if platform:
        conditions.append("platform=?")
        params.append(platform)
    if category:
        conditions.append("category=?")
        params.append(category)
    if status:
        conditions.append("status=?")
        params.append(status)
    if min_oem > 0:
        conditions.append("oem_score>=?")
        params.append(min_oem)
    if min_followers > 0:
        conditions.append("followers>=?")
        params.append(min_followers)
    where = " AND ".join(conditions) if conditions else "1=1"
    rows = conn.execute(f"SELECT * FROM leads WHERE {where} ORDER BY oem_score DESC LIMIT ?", params + [limit]).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_status(lead_id: int, status: str, notes: str = ""):
    conn = get_conn()
    conn.execute("UPDATE leads SET status=?, notes=?, updated_at=? WHERE id=?", (status, notes, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), lead_id))
    conn.commit()
    conn.close()


def get_stats() -> dict:
    """获取统计概览"""
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    by_platform = {r["platform"]: r["cnt"] for r in conn.execute("SELECT platform, COUNT(*) as cnt FROM leads GROUP BY platform").fetchall()}
    by_category = {r["category"]: r["cnt"] for r in conn.execute("SELECT category, COUNT(*) as cnt FROM leads WHERE category IS NOT NULL GROUP BY category").fetchall()}
    by_status = {r["status"]: r["cnt"] for r in conn.execute("SELECT status, COUNT(*) as cnt FROM leads GROUP BY status").fetchall()}
    conn.close()
    return {"total": total, "by_platform": by_platform, "by_category": by_category, "by_status": by_status}
