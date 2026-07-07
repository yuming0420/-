# -*- coding: utf-8 -*-
"""Agent 智能层 - LLM驱动的达人数据解析"""

import json
import os
from openai import OpenAI
from typing import Optional


class AgentExtractor:
    """使用 LLM 从原始达人数据中智能提取结构化信息"""

    EXTRACT_PROMPT = """你是一个电商达人分析专家，服务于一家大健康食品 OEM/ODM 代工企业。
该企业的核心业务是：为品牌方代工生产健康食品、功能性食品、保健品、代餐、滋补品等。
你需要严格判断一个达人是否是该企业的潜在合作对象（即达人本身有带货健康食品类产品的能力和受众）。

## 目标客户画像（极其重要）
目标客户必须是**内容与健康/食品/养生/减脂/健身/母婴营养直接相关的个体达人**。
以下类型**不是**目标客户，无论粉丝多少：
- 娱乐搞笑/剧情/颜值/才艺类达人（即使偶尔发过美食内容）
- MCN机构/传媒公司/公会/直播公司（他们是服务方，不是带货达人）
- 纯粹的企业号/品牌号
- 泛生活 vlog 博主（内容太分散，没有健康食品垂直受众）
- 探店/吃播类达人（除非主攻健康食品测评方向）

## 身份判断
首先判断该账号是"个体达人"还是"MCN/机构/传媒公司"：
- 个体达人：个人创作者，内容以个人IP为核心，面向C端消费者
- MCN/机构：简介中出现"传媒""MCN""经纪""孵化""机构""公会""公司""直播公司""文化传播"等关键词，或内容涉及达人招募/行业培训/账号代运营

## 提取字段
1. account_type: "creator"（个体达人）或 "mcn"（MCN/机构/传媒公司）
2. email: 邮箱地址（从简介或商务合作栏提取）
3. wechat: 微信号（从简介提取，常见格式: VX/微信/vx/wx + 字母数字组合）
4. phone: 手机号（通常在商务合作栏，如无则填 null）
5. contact_source: 联系方式来源（bio/comment/manual）
6. category: 赛道分类，从以下选项选一个最匹配的: {categories}
   判断标准：以达人**持续输出的核心内容主题**为准，不是看他简介里写过什么词。
   如果达人内容与所有赛道都不匹配（如纯粹娱乐/剧情/颜值/传媒公司日常），
   则填写最后一个选项"其他/不相关"。
7. tags: 内容标签，最多5个，以数组返回
8. oem_score: 大健康食品OEM合作潜力评分(0-100)，评分标准:
   - 内容-业务匹配度(0-40): 这是最关键维度。
     * 达人内容直接围绕健康饮食/营养科普/减脂餐/养生/保健品测评 → 30-40
     * 达人内容涉及美食/做饭但对健康有侧重 → 15-30
     * 达人内容是泛美食/吃播/探店，无健康侧重 → 5-15
     * 达人内容与食品无关（娱乐/剧情/颜值/传媒）→ 0-5
   - 目标受众精准度(0-25): 粉丝画像是否与健康食品消费者重叠
     * 粉丝主要是25-45岁关注健康的女性 → 20-25
     * 粉丝画像分散或偏年轻娱乐 → 5-15
   - 互动质量(0-20): 评论是否有产品咨询/求链接等购买意图，而非纯表情/夸赞
   - 商业可信度(0-15): 账号是否有规范的商务合作入口、内容制作精良、无低质搬运
   注意：粉丝量不作为主要评分依据——1万精准粉丝的价值远超100万泛粉。
9. oem_reason: 评分简要理由（聚焦"内容是否与大健康食品相关"）
10. intent_signal: 合作意向信号描述（如简介写了"欢迎合作""商务联系"等）
11. intent_level: 意向等级(high/medium/low)
12. summary: 一句话摘要(20字以内)
13. mcn_focus: 仅当 account_type 为 "mcn" 时填写。推断该 MCN/机构主攻的赛道和产品方向。
    如果账号是达人则填 null。
14. mcn_relevance: 仅当 account_type 为 "mcn" 时填写。该机构业务与大健康 OEM 代工的匹配度(0-100)。
    评分维度: 如果其签约达人集中在健康食品/保健品/母婴营养赛道 → 70+，
    美妆/个护/生活方式 → 40-69，娱乐/游戏/剧情 → <40。
    如果账号是达人则填 null。

## 原始数据
{raw_data}

## 要求
- 只返回 JSON，不要有其他文字
- 所有字段都必须存在，无信息则填 null
- oem_score 和 mcn_relevance 必须是 0-100 的数字
- category 如无法匹配任何预设赛道则填 "其他/不相关"
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
        """启发式 OEM 评分 - 以内容匹配度为核心，粉丝量仅作微调"""
        score = 25.0  # 基准分偏低，表示需要证据支撑
        bio = (data.get("bio") or data.get("desc") or data.get("signature") or "").lower()
        nickname = (data.get("nickname") or data.get("name") or "").lower()

        # --- 内容匹配度 (最关键维度) ---
        health_keywords = [
            "健康", "营养", "减脂", "减肥", "养生", "保健", "滋补", "代餐",
            "低卡", "无糖", "控糖", "膳食", "食疗", "草本", "功能性食品",
            "蛋白质", "维生素", "肠道", "益生菌", "酵素", "轻食", "超级食物",
            "健身餐", "增肌", "健康饮食", "clean eating", "diet", "nutrition",
        ]
        food_general = ["美食", "做饭", "吃播", "料理", "烘焙", "探店", "零食", "吃货"]
        mcn_signals = ["传媒", "mcn", "经纪", "孵化", "公会", "机构", "直播公司", "文化传播",
                       "代运营", "招募", "素人", "主播培训", "陪跑"]

        # 减分: MCN/机构信号
        for kw in mcn_signals:
            if kw in bio or kw in nickname:
                score -= 20
                break

        # 加分: 健康食品垂直关键词
        health_hits = sum(1 for kw in health_keywords if kw in bio)
        if health_hits >= 3:
            score += 35
        elif health_hits >= 1:
            score += 20

        # 泛美食但没有健康侧重 → 不加分
        if health_hits == 0:
            food_hits = sum(1 for kw in food_general if kw in bio)
            if food_hits > 0:
                score += 5  # 仅微调

        # --- 互动率微调 ---
        followers = int(data.get("followers", 0) or 0)
        likes = int(data.get("avg_likes", 0) or 0)
        if followers > 0 and likes > 0:
            rate = likes / followers
            if rate > 0.1: score += 10
            elif rate > 0.05: score += 5

        # --- 联系方式奖励 ---
        import re
        if re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', bio):
            score += 5
        if re.search(r'(?:VX|vx|wx|微信|WeChat)\s*[:：]?\s*([a-zA-Z0-9_-]{5,20})', bio):
            score += 5

        return min(max(score, 0.0), 100.0)
