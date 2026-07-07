# -*- coding: utf-8 -*-
"""导出层 - 数据导出为 Excel / CSV"""

import os
import pandas as pd
from datetime import datetime
from typing import Optional


class Exporter:
    """将 leads 数据导出为 Excel 或 CSV"""

    COLUMN_MAP = {
        "id": "ID",
        "platform": "平台",
        "user_id": "用户ID",
        "nickname": "昵称",
        "followers": "粉丝数",
        "avg_likes": "平均点赞",
        "email": "邮箱",
        "wechat": "微信号",
        "phone": "手机号",
        "category": "赛道",
        "tags": "标签",
        "oem_score": "OEM评分",
        "oem_reason": "评分理由",
        "intent_signal": "意向信号",
        "intent_level": "意向等级",
        "account_type": "账号类型",
        "mcn_focus": "MCN主攻赛道",
        "mcn_relevance": "MCN匹配度",
        "bio": "简介",
        "homepage_url": "主页链接",
        "status": "跟进状态",
        "notes": "备注",
        "contact_source": "联系方式来源",
        "created_at": "创建时间",
        "updated_at": "更新时间",
    }

    def __init__(self, config: dict):
        cfg = config.get("export", {})
        self.default_format = cfg.get("default_format", "xlsx")
        self.output_dir = os.path.expanduser(cfg.get("output_dir", "./output"))
        os.makedirs(self.output_dir, exist_ok=True)

    def export(self, leads: list[dict], filename: Optional[str] = None, fmt: Optional[str] = None) -> str:
        """导出 lead 列表到文件"""
        fmt = fmt or self.default_format
        if not filename:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"达人名单_{ts}"

        df = pd.DataFrame(leads)
        existing_cols = [c for c in self.COLUMN_MAP if c in df.columns]
        df = df[existing_cols].rename(columns={c: self.COLUMN_MAP[c] for c in existing_cols})

        if fmt == "xlsx":
            path = os.path.join(self.output_dir, f"{filename}.xlsx")
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="达人名单")
                ws = writer.sheets["达人名单"]
                for i, col in enumerate(df.columns):
                    max_len = max(df[col].fillna("").astype(str).map(len).max(), len(col)) + 2
                    ws.column_dimensions[chr(65 + i) if i < 26 else f"A{chr(65 + i - 26)}"].width = min(max_len, 40)
        elif fmt == "csv":
            path = os.path.join(self.output_dir, f"{filename}.csv")
            df.to_csv(path, index=False, encoding="utf-8-sig")
        else:
            raise ValueError(f"不支持的导出格式: {fmt}，可选 xlsx / csv")

        print(f"[Export] 已导出 {len(leads)} 条记录到 {path}")
        return path
