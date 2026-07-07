# -*- coding: utf-8 -*-
"""Agent 智能层 - LLM驱动的达人数据解析"""

import json
import os
from openai import OpenAI
from typing import Optional


class AgentExtractor:
    """使用 LLM 从原始达人数据中智能提取结构化信息"""

    EXTRACT_PROMPT = """你是一个电商达人分析专家，服务于一家大健康食品 OEM/ODM 代工企业（山东朱氏药业）。
请从给定的达人社媒主页数据中提取以下信息，以 JSON 格式返回。

## 身份判断
首先判断该账号是"个体达人"还是"MCN/机构/传媒公司"：
- 个体达人：个人创作者，内容是日常生活/知识分享/带货
- MCN/机构：简介中出现"传媒""MCN""经纪""孵化""机构""公会""公司""科技"等关键词，或内容涉及达人招募/行业培训/商业服务

## 提取字段
1. account_type: "creator"（个体达人）或 "mcn"（MCN/机构/传媒公司）
2. email: 邮箱地址（从简介或商务合作栏提取）
3. wechat: 微信号（从简介提取，常见格式: VX/微信/vx/wx + 字母数字组合）
4. phone: 手机号（通常在商务合作栏，如无则填 null）
5. contact_source: 联系方式来源（bio/comment/manual）
6. category: 赛道分类，从以下选项选一个最匹配的: {categories}
7. tags: 内容标签，最多5个，以数组返回
8. oem_score: OEM合作潜力评分(0-100)，评分标准:
   - 粉丝量(0-30): <1万得5, 1-10万得10, 10-50万得20, >50万得30
   - 内容垂直度(0-25): 专注于单一赛道得高分
   - 互动率(0-25): 点赞/粉丝比 >5%得20+
   - 品牌合作历史(0-20): 主页可见商务合作痕迹
9. oem_reason: 评分简要理由(一句话)
10. intent_signal: 合作意向信号描述（如简介写了"欢迎合作""商务联系"等）
11. intent_level: 意向等级(high/medium/low)
12. summary: 一句话摘要(20字以内)
13. mcn_focus: 仅当 account_type 为 "mcn" 时填写。推断该 MCN/机构主攻的赛道和产品方向，
    例如"健康食品/美妆护肤/服饰穿搭/本地生活"。如果账号是达人则填 null。
14. mcn_relevance: 仅当 account_type 为 "mcn" 时填写。该机构业务与大健康 OEM 代工的匹配度(0-100)。
    评分维度: 如果其主攻赛道与健康食品/代餐/保健品/功能性食品相关则高分(70+)，
    与美妆/母婴相关则中等(40-69)，与数码/游戏等无关则低分(<40)。
    如果账号是达人则填 null。

## 原始数据
{raw_data}

## 要求
- 只返回 JSON，不要有其他文字
- 所有字段都必须存在，无信息则填 null
- oem_score 和 mcn_relevance 必须是 0-100 的数字
"""

    def __init__(self, config: dict):
        cfg = config.get("agent", {})
        api_key = os.getenv(cfg.get("api_key_env", "OPENAI_API_KEY"), "")
        base_url = cfg.get("api_base") or None
        self.client = OpenAI(api_key=api_key, base_url=base_url) if api_key else None
        self.model = cfg.get("model", "gpt-4o-mini")
        self.temperature = cfg.get("temperature", 0.1)
        self.max_tokens = cfg.get("max_tokens", 2000)
        self.caps = cfg.get("capabilities", {})
        self.categories = config.get("categories", [])

    def extract_from_profile(self, raw_data: dict) -> dict:
        """从达人主页数据中提取所有关键信息"""
        if not self.client:
            return self._fallback_extract(raw_data)

        categories_list = ", ".join(self.categories) if self.categories else "请根据内容自动分类"
        prompt = self.EXTRACT_PROMPT.format(
            categories=categories_list,
            raw_data=json.dumps(raw_data, ensure_ascii=False, indent=2)
        )
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            content = response.choices[0].message.content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("\n```", 1)[0]
            return json.loads(content)
        except Exception as e:
            print(f"[Agent] LLM提取失败: {e}, 使用降级方案")
            return self._fallback_extract(raw_data)

    def batch_extract_comments(self, comments: list[dict]) -> list[dict]:
        """批量分析评论区，识别合作意向"""
        if not self.client or not self.caps.get("identify_intent"):
            return comments

        prompt = f"""分析以下达人评论区，找出所有表达合作意向的评论。
合作意向包括: 询价、求合作、问怎么买、想代理等。
以 JSON 数组返回，每个元素包含 comment_index(索引)、intent_type(意向类型)、summary(内容摘要)。

评论列表:
{json.dumps(comments, ensure_ascii=False, indent=2)}
"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=2000
            )
            content = response.choices[0].message.content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("\n```", 1)[0]
            return json.loads(content)
        except Exception as e:
            print(f"[Agent] 评论分析失败: {e}")
            return []

    def _fallback_extract(self, raw_data: dict) -> dict:
        """无 LLM 时的降级提取方案 - 正则匹配"""
        import re
        bio = raw_data.get("bio") or raw_data.get("desc") or ""
        nickname = raw_data.get("nickname") or raw_data.get("name") or ""

        email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', bio)
        wechat_match = re.search(r'(?:VX|vx|wx|微信|WeChat)\s*[:：]?\s*([a-zA-Z0-9_-]{5,20})', bio)
        phone_match = re.search(r'1[3-9]\d{9}', bio)

        intent_keywords = ["合作", "商务", "联系", "对接", "带货", "代理"]
        has_intent = any(kw in bio for kw in intent_keywords)

        return {
            "email": email_match.group(0) if email_match else None,
            "wechat": wechat_match.group(1) if wechat_match else None,
            "phone": phone_match.group(0) if phone_match else None,
            "contact_source": "bio" if any([email_match, wechat_match, phone_match]) else None,
            "category": None,
            "tags": [],
            "oem_score": self._heuristic_oem(raw_data),
            "oem_reason": "降级评估(无LLM)",
            "intent_signal": "简介含合作关键词" if has_intent else None,
            "intent_level": "high" if has_intent else "low",
            "summary": f"{nickname}, 粉丝{raw_data.get('followers',0)}",
            "account_type": "mcn" if any(kw in bio for kw in ["传媒", "MCN", "经纪", "孵化", "机构"]) else "creator",
            "mcn_focus": None,
            "mcn_relevance": None,
        }

    def _heuristic_oem(self, data: dict) -> float:
        """启发式 OEM 评分,无需 LLM"""
        score = 0.0
        followers = int(data.get("followers", 0))
        if followers < 10000: score += 5
        elif followers < 100000: score += 10
        elif followers < 500000: score += 20
        else: score += 30

        likes = int(data.get("avg_likes", 0))
        if followers > 0 and likes > 0:
            rate = likes / followers
            if rate > 0.1: score += 25
            elif rate > 0.05: score += 15
            elif rate > 0.02: score += 10
            else: score += 5

        return min(score, 100.0)
