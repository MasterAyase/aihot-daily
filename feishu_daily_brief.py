# -*- coding: utf-8 -*-
"""
每日 AI 热点简报 → 飞书群自动推送
每天9点由 Windows 任务计划程序触发
功能：aihot API 取近24h热点 → 格式化为飞书卡片 → 推送到飞书群 → 保存本地 md
"""
import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

# ====== 配置 ======
FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK", "https://open.feishu.cn/open-apis/bot/v2/hook/6fbda3b2-0541-4efb-8561-2c89d66569e3")
FEISHU_KEYWORD = "AI资讯"  # 飞书机器人自定义关键词
AIHOT_BASE = "https://aihot.virxact.com"
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", os.path.dirname(os.path.abspath(__file__)))  # 简报 md 保存目录
TZ_SH = timezone(timedelta(hours=8))  # 北京时间

# ====== aihot API 调用 ======
def aihot_get(path):
    url = AIHOT_BASE + path
    req = urllib.request.Request(url, headers={"User-Agent": "aihot-daily-brief/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[aihot] 请求失败 {path}: {e}")
        return None

def fetch_hot_topics():
    return aihot_get("/api/v1/hot-topics")

def fetch_items_24h():
    return aihot_get("/api/v1/items?mode=selected&window=24h&limit=20")

def fetch_story(public_id):
    return aihot_get(f"/api/v1/stories/{public_id}")

def extract_story_id(topic):
    """从 hot-topics 条目的 links.story 提取 publicId"""
    links = topic.get("links", {})
    story_url = links.get("story", "")
    if story_url and "/story/" in story_url:
        return story_url.rstrip("/").split("/story/")[-1]
    return None

# ====== 时间格式化 ======
def to_beijing_time(iso_str):
    """ISO 时间转北京时间字符串"""
    if not iso_str:
        return "时间不详"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        dt_sh = dt.astimezone(TZ_SH)
        return dt_sh.strftime("%m月%d日 %H:%M")
    except Exception:
        return iso_str

def today_str():
    return datetime.now(TZ_SH).strftime("%Y.%-m.%-d") if hasattr(datetime, "now") else datetime.now(TZ_SH).strftime("%Y.%m.%d")

def today_log():
    return datetime.now(TZ_SH).strftime("%Y-%m-%d %H:%M:%S")

# ====== 飞书推送 ======
def send_feishu(card):
    """发送飞书交互卡片"""
    payload = {
        "msg_type": "interactive",
        "card": card
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        FEISHU_WEBHOOK,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if result.get("StatusCode") == 0 or result.get("code") == 0:
                print(f"[feishu] 推送成功")
                return True
            else:
                print(f"[feishu] 推送失败: {result}")
                return False
    except Exception as e:
        print(f"[feishu] 推送异常: {e}")
        return False

def send_feishu_text(text):
    """发送纯文本消息（兜底用）"""
    payload = {"msg_type": "text", "content": {"text": text}}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        FEISHU_WEBHOOK,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[feishu] 文本推送异常: {e}")
        return None

# ====== 构建飞书卡片 ======
def build_card(hot_topics_data, items_data):
    today = datetime.now(TZ_SH).strftime("%Y年%m月%d日")
    
    # --- 卡片头部 ---
    header = {
        "title": {
            "tag": "plain_text",
            "content": f"AI资讯日报 | {today}"
        },
        "template": "blue"
    }
    
    elements = []
    
    # --- 引导语（必须包含关键词「AI资讯」）---
    elements.append({
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": f"**今日AI资讯简报** · 以下为近24小时AI圈最热动态\n如需生成完整长文，请在 Trae 内说「按今天的热点写两篇」"
        }
    })
    elements.append({"tag": "hr"})
    
    # --- 当前最热话题 ---
    hot_items = hot_topics_data.get("items", []) if hot_topics_data else []
    
    if hot_items:
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": "🔥 **当前最热**"}
        })
        
        for i, topic in enumerate(hot_items[:3], 1):
            title = topic.get("title", "无标题")
            source_count = topic.get("sourceCount", 0)
            signal_count = topic.get("signalCount", 0)
            latest_at = to_beijing_time(topic.get("latestAt"))
            aihot_link = topic.get("links", {}).get("aihot", "")
            
            # 卡片内容
            content = f"**{i}. [{title}]({aihot_link})**\n"
            content += f"信源 {source_count} · 信号 {signal_count} · 最新 {latest_at}\n"
            
            # 附带事件摘要（如果有）
            story_id = extract_story_id(topic)
            if story_id:
                story = fetch_story(story_id)
                if story and story.get("story", {}).get("digest"):
                    digest = story["story"]["digest"]
                    # 截断长摘要
                    if len(digest) > 300:
                        digest = digest[:300] + "..."
                    content += f"\n{digest}"
            
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": content}
            })
        
        elements.append({"tag": "hr"})
    
    # --- 近24小时精选资讯 ---
    items = items_data.get("items", []) if items_data else []
    
    if items:
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": "📰 **近24小时精选**"}
        })
        
        for i, item in enumerate(items[:8], 1):
            title = item.get("title", "无标题")
            source = item.get("source", {}).get("name", "未知来源")
            published = to_beijing_time(item.get("publishedAt") or item.get("discoveredAt"))
            aihot_link = item.get("links", {}).get("aihot", "")
            summary = item.get("summary", "") or ""
            
            if len(summary) > 120:
                summary = summary[:120] + "..."
            
            content = f"**{i}. [{title}]({aihot_link})**\n"
            content += f"{source} · {published}"
            if summary:
                content += f"\n{summary}"
            
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": content}
            })
    elif not hot_items:
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": "今日暂无热点数据"}
        })
    
    # --- 底部 ---
    elements.append({"tag": "hr"})
    elements.append({
        "tag": "note",
        "elements": [
            {"tag": "plain_text", "content": f"数据来源：AI HOT (aihot.virxact.com) · 推送时间 {datetime.now(TZ_SH).strftime('%H:%M')}"}
        ]
    })
    
    return {
        "config": {"wide_screen_mode": True, "enable_forward": True},
        "header": header,
        "elements": elements
    }

# ====== 保存本地 md ======
def save_brief_md(hot_topics_data, items_data):
    today = datetime.now(TZ_SH).strftime("%Y.%m.%d")
    filename = f"{today}_daily_brief.md"
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    lines = [f"# AI资讯日报 | {today}\n"]
    lines.append(f"> 推送时间：{today_log()}\n")
    lines.append(f"> 数据来源：AI HOT (aihot.virxact.com)\n\n---\n")
    
    hot_items = hot_topics_data.get("items", []) if hot_topics_data else []
    if hot_items:
        lines.append("## 当前最热\n")
        for i, topic in enumerate(hot_items[:5], 1):
            title = topic.get("title", "无标题")
            source_count = topic.get("sourceCount", 0)
            latest_at = to_beijing_time(topic.get("latestAt"))
            aihot_link = topic.get("links", {}).get("aihot", "")
            lines.append(f"{i}. [{title}]({aihot_link})")
            lines.append(f"   - 信源 {source_count} · 最新 {latest_at}\n")
    
    items = items_data.get("items", []) if items_data else []
    if items:
        lines.append("## 近24小时精选\n")
        for i, item in enumerate(items[:15], 1):
            title = item.get("title", "无标题")
            source = item.get("source", {}).get("name", "未知来源")
            published = to_beijing_time(item.get("publishedAt") or item.get("discoveredAt"))
            aihot_link = item.get("links", {}).get("aihot", "")
            summary = item.get("summary", "") or ""
            lines.append(f"{i}. [{title}]({aihot_link})")
            lines.append(f"   - {source} · {published}")
            if summary:
                lines.append(f"   - {summary}")
            lines.append("")
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[local] 简报已保存：{filepath}")

# ====== 主流程 ======
def main():
    print(f"=== AI资讯日报 {today_log()} ===")
    
    # 1. 获取热点数据
    print("[1/4] 获取当前热点...")
    hot_topics = fetch_hot_topics()
    print(f"  热点数：{len(hot_topics.get('items', [])) if hot_topics else 0}")
    
    print("[2/4] 获取近24h精选...")
    items_24h = fetch_items_24h()
    print(f"  精选数：{len(items_24h.get('items', [])) if items_24h else 0}")
    
    # 3. 构建卡片
    print("[3/4] 构建飞书卡片...")
    card = build_card(hot_topics, items_24h)
    
    # 4. 推送飞书
    print("[4/4] 推送到飞书群...")
    success = send_feishu(card)
    
    # 5. 保存本地 md
    save_brief_md(hot_topics, items_24h)
    
    if success:
        print("=== 完成 ===")
    else:
        print("=== 飞书推送失败，但本地简报已保存 ===")

if __name__ == "__main__":
    main()
