"""
路线规划 Agent 服务
- ReAct 循环调用 route_tools.py 里的 6 个工具
- SSE 流式返回给前端
- 对话历史存 db.py
"""
import os
import json
import re
import requests
import tiktoken
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from datetime import datetime, timedelta
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_PATH)

from route_tools import TOOLS_SCHEMA, TOOL_FUNCTIONS
from db import SessionLocal, Conversation, Message

# ==================== FastAPI ====================
app = FastAPI(title="路线规划 Agent", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_TOKENS = 4096


# ==================== 工具函数 ====================
def clean_answer(text):
    """清理模型输出：去掉JSON代码块、大括号、多余符号"""
    if not text:
        return text
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```', '', text)
    if '{' in text and '}' in text:
        idx = text.find('{')
        before = text[:idx].strip()
        if before:
            text = before
        else:
            text = text.replace('{', '').replace('}', '')
            text = text.replace('"', '').replace('":', '：').replace(',', '；')
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
    return text.strip()


SYSTEM_PROMPT = """你是汕头旅游助手，有两种回答模式：

【路线规划模式】
当用户说"推荐路线""玩几天""怎么安排行程"等需要规划行程时：
1. 判断条件：
   - 有明确条件（主题、人群、区域）→ 调 search_spots_by_graph
   - 只有模糊描述（"有侨乡味道""红色景点"）→ 调 search_spots_by_vector
2. 拿到景点后用 plan_route 排路线
3. 输出时间块格式，严格使用 plan_route 返回的 arrive_time / leave_time
   - 格式：09:00｜早餐 福合埕牛肉丸
   - 不要自己编时间，一切以工具返回为准
   - 时间块必须严格按 arrive_time 升序输出（先到先列，不得打乱顺序）
   - 每个景点时间块后附 1-2 句该地点介绍（用工具返回的 description 提炼），让路线既有安排也有内容
   - 早餐/餐饮/休息等非工具返回的时段，只能放在当天第一个景点之前或最后一个景点之后，不得插入景点时间块之间
4. 必须处理 time_warning 字段（不是 null 就要处理）：
   - 出现 time_warning 时，先自行调整行程使安排可行（顺延到达时间、调整景点顺序、替换景点），实在无法调整才原样提示用户
   - "XX 才开门，到达太早" → 已自动顺延到开门时间，或先安排附近景点
   - "演出仅在周X/周Y有，今日周Z无演出，不建议硬排" → 该演出今天看不到，直接将其从行程中移除或明确改期，不要硬排
   - plan_route 返回 today_unavailable: true 的景点 → 今天不可安排（闭馆/无演出），直接从行程中移除或改期
   - "周一闭馆" 这类备注 → 只有当天确实是闭馆日才提示，非闭馆日不要提
5. 用户明确点名要看的内容（如"想看英歌舞"），若知识库查不到具体场次，必须主动调 web_search 联网查一次并给出结果，不要反问用户要不要查
6. 如果整天有多个 time_warning，最后统一汇总提醒

【自由问答模式】
当用户追问"XX景点怎么样""XX在哪里""多少钱"等具体问题时：
直接调 get_spot_detail 或 web_search，像聊天一样自然回答，不用走时间块格式。

【可用工具】
- search_spots_by_graph(theme_name, group_name, district, max_duration) - 结构化查询
- search_spots_by_vector(query) - 语义检索
- get_spot_detail(name) - 查景点详情
- plan_route(spot_names, days) - 规划路线，返回值带 arrive_time / leave_time / time_warning
- nearby_recommend(name, radius_km) - 附近推荐
- web_search(query) - 联网查实时信息

【通用要求】
- 不要输出JSON、大括号、引号
- 不要用markdown加粗、代码块
- 基于工具返回的真实信息回答
- 简洁自然
- 用户明确要求但知识库查不到的信息（如具体店铺、最新活动），应主动调 web_search 查询后再回答，不要反问用户要不要查"""


def count_tokens(text):
    try:
        enc = tiktoken.encoding_for_model("gpt-3.5-turbo")
        return len(enc.encode(text))
    except:
        return len(text) // 2


def trim_messages(messages, max_tokens=MAX_TOKENS):
    system = messages[0]
    history = messages[1:]
    kept = []
    total = count_tokens(system["content"])
    for msg in reversed(history):
        content = msg.get("content", "") or ""
        if isinstance(content, list):
            content = str(content)
        t = count_tokens(content)
        if total + t > max_tokens:
            break
        kept.insert(0, msg)
        total += t
    return [system] + kept


def get_or_create_conv(db, conversation_id, query):
    """
    统一获取/创建 conversation 的逻辑：
    - id 有效（>0）→ 查
    - 查不到 → 新建
    - id 为空 → 新建
    """
    conv = None
    if conversation_id and conversation_id > 0:
        conv = db.query(Conversation).get(conversation_id)
    if not conv:
        conv = Conversation(title=query[:30])
        db.add(conv); db.commit(); db.refresh(conv)
    return conv


class AgentRouteRequest(BaseModel):
    user_query: str
    conversation_id: Optional[int] = None


# ==================== 对话管理接口 ====================
@app.post("/api/agent/conversations")
def create_conversation():
    db = SessionLocal()
    conv = Conversation(title="新对话")
    db.add(conv); db.commit(); db.refresh(conv)
    return {"id": conv.id, "title": conv.title}


@app.get("/api/agent/conversations")
def list_conversations():
    db = SessionLocal()
    convs = db.query(Conversation).order_by(Conversation.updated_at.desc()).all()
    return [{"id": c.id, "title": c.title, "updated_at": c.updated_at.isoformat()} for c in convs]


@app.get("/api/agent/conversations/{conv_id}/messages")
def get_messages(conv_id: int):
    db = SessionLocal()
    conv = db.query(Conversation).get(conv_id)
    if not conv:
        return {"messages": [], "memory": {}}
    msgs = [{"role": m.role, "content": m.content} for m in conv.messages]
    return {"messages": msgs, "memory": conv.memory or {}}


@app.delete("/api/agent/conversations/{conv_id}")
def delete_conversation(conv_id: int):
    db = SessionLocal()
    conv = db.query(Conversation).get(conv_id)
    if conv:
        db.query(Message).filter(Message.conversation_id == conv_id).delete()
        db.delete(conv); db.commit()
    return {"success": True}


# ==================== 非流式 Agent ====================
@app.post("/api/agent_route")
async def agent_route(req: AgentRouteRequest):
    db = SessionLocal()
    api_key = os.getenv("DEEPSEEK_API_KEY")
    api_url = "https://api.deepseek.com/chat/completions"
    model = "deepseek-chat"

    conv = get_or_create_conv(db, req.conversation_id, req.user_query)

    history = db.query(Message).filter(Message.conversation_id == conv.id).order_by(Message.id).all()
    memory = conv.memory or {}

    system_content = SYSTEM_PROMPT
    if memory:
        system_content += f"\n\n【用户记忆】{json.dumps(memory, ensure_ascii=False)}"
    # 注入真实日期/星期：规划行程时必须考虑演出场次与闭馆日（2026-09-26 新增）
    today = datetime.now()
    weekday_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][today.weekday()]
    system_content += f"\n\n【今天是】{today.strftime('%Y-%m-%d')}（{weekday_cn}）。规划行程时必须考虑今天星期几（演出场次、闭馆日等）。"

    messages = [{"role": "system", "content": system_content}]
    for m in history:
        messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": req.user_query})
    messages = trim_messages(messages)

    user_msg = Message(conversation_id=conv.id, role="user", content=req.user_query)
    db.add(user_msg); db.commit()

    try:
        for step in range(5):
            resp = requests.post(api_url, headers={
                "Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
            }, json={
                "model": model, "messages": messages,
                "tools": TOOLS_SCHEMA, "tool_choice": "auto",
                "temperature": 0.7, "max_tokens": MAX_TOKENS,
            }, timeout=90)
            data = resp.json()
            msg = data["choices"][0]["message"]

            if not msg.get("tool_calls"):
                answer = msg["content"]
                ai_msg = Message(conversation_id=conv.id, role="assistant", content=answer)
                db.add(ai_msg); db.commit()

                if not conv.title or conv.title == "新对话":
                    try:
                        title_resp = requests.post(api_url, headers={
                            "Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
                        }, json={
                            "model": model,
                            "messages": [
                                {"role": "system", "content": "用8个字以内总结用户的旅行需求，直接输出标题，不要标点。"},
                                {"role": "user", "content": req.user_query}
                            ],
                            "max_tokens": 20,
                        }, timeout=15)
                        conv.title = title_resp.json()["choices"][0]["message"]["content"].strip()
                        db.commit()
                    except:
                        pass

                return {"success": True, "answer": clean_answer(answer),
                        "steps_taken": step + 1, "conversation_id": conv.id}

            messages.append(msg)
            for tool_call in msg["tool_calls"]:
                func_name = tool_call["function"]["name"]
                func_args = json.loads(tool_call["function"]["arguments"])
                result = TOOL_FUNCTIONS.get(func_name, lambda **kw: {})(**func_args)
                messages.append({
                    "role": "tool", "tool_call_id": tool_call["id"],
                    "name": func_name,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                })

        messages.append({"role": "user", "content": "请根据以上信息直接输出最终路线推荐。"})
        resp = requests.post(api_url, headers={
            "Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
        }, json={"model": model, "messages": messages, "temperature": 0.7, "max_tokens": MAX_TOKENS}, timeout=60)
        answer = resp.json()["choices"][0]["message"]["content"]
        ai_msg = Message(conversation_id=conv.id, role="assistant", content=answer)
        db.add(ai_msg); db.commit()
        return {"success": True, "answer": answer, "steps_taken": 5, "conversation_id": conv.id}

    except Exception as e:
        print(f"[Agent] 错误: {e}")
        return {"success": False, "error": str(e), "conversation_id": conv.id}


# ==================== SSE 流式 Agent ====================
@app.post("/api/agent_route_stream")
async def agent_route_stream(req: AgentRouteRequest):
    db = SessionLocal()
    api_key = os.getenv("DEEPSEEK_API_KEY")
    api_url = "https://api.deepseek.com/chat/completions"
    model = "deepseek-chat"

    cache_key = req.user_query.strip()
    if hasattr(agent_route_stream, '_cache') and cache_key in agent_route_stream._cache:
        cached = agent_route_stream._cache[cache_key]
        def cached_gen():
            yield f"data: {json.dumps({'type': 'meta', 'conversation_id': req.conversation_id or 0, 'steps': 0, 'cached': True})}\n\n"
            for i in range(0, len(cached), 5):
                yield f"data: {json.dumps({'type': 'chunk', 'text': cached[i:i+5]})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return StreamingResponse(cached_gen(), media_type="text/event-stream")

    # ★ 统一走 get_or_create_conv，带 id>0 校验
    conv = get_or_create_conv(db, req.conversation_id, req.user_query)

    history = db.query(Message).filter(Message.conversation_id == conv.id).order_by(Message.id).all()
    memory = conv.memory or {}

    system_content = SYSTEM_PROMPT
    if memory:
        system_content += f"\n\n【用户记忆】{json.dumps(memory, ensure_ascii=False)}"
    # 注入真实日期/星期：规划行程时必须考虑演出场次与闭馆日（2026-09-26 新增）
    today = datetime.now()
    weekday_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][today.weekday()]
    system_content += f"\n\n【今天是】{today.strftime('%Y-%m-%d')}（{weekday_cn}）。规划行程时必须考虑今天星期几（演出场次、闭馆日等）。"

    messages = [{"role": "system", "content": system_content}]
    for m in history:
        messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": req.user_query})
    messages = trim_messages(messages)

    user_msg = Message(conversation_id=conv.id, role="user", content=req.user_query)
    db.add(user_msg); db.commit()

    async def generate():
        nonlocal messages
        steps = 0
        final_text = ""

        # ★ meta 只推一次，放在最前面
        yield f"data: {json.dumps({'type': 'meta', 'conversation_id': conv.id, 'steps': 0})}\n\n"
        yield f"data: {json.dumps({'type': 'step', 'text': '理解你的需求...'})}\n\n"

        for step in range(5):
            try:
                resp = requests.post(api_url, headers={
                    "Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
                }, json={
                    "model": model, "messages": messages,
                    "tools": TOOLS_SCHEMA, "tool_choice": "auto",
                    "temperature": 0.7, "max_tokens": MAX_TOKENS,
                }, timeout=90)
                data = resp.json()
                msg = data["choices"][0]["message"]

                if not msg.get("tool_calls"):
                    final_text = msg["content"]
                    steps = step + 1
                    break

                messages.append(msg)
                for tool_call in msg["tool_calls"]:
                    func_name = tool_call["function"]["name"]
                    func_args = json.loads(tool_call["function"]["arguments"])

                    tool_names = {
                        "search_spots_by_graph":  "图谱搜索景点",
                        "search_spots_by_vector": "语义检索景点",
                        "get_spot_detail":        "查景点详情",
                        "plan_route":             "规划路线",
                        "nearby_recommend":       "附近推荐",
                        "web_search":             "联网搜索",
                    }
                    label = tool_names.get(func_name, func_name)
                    yield f"data: {json.dumps({'type': 'tool', 'text': f'{label}...'})}\n\n"

                    result = TOOL_FUNCTIONS.get(func_name, lambda **kw: {})(**func_args)

                    messages.append({
                        "role": "tool", "tool_call_id": tool_call["id"],
                        "name": func_name,
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    })
            except Exception as e:
                final_text = f"出错了：{e}"
                break

        if not final_text:
            final_text = "未能生成路线，请重试"

        final_text = clean_answer(final_text)

        ai_msg = Message(conversation_id=conv.id, role="assistant", content=final_text)
        db.add(ai_msg); db.commit()

        if not hasattr(agent_route_stream, '_cache'):
            agent_route_stream._cache = {}
        agent_route_stream._cache[cache_key] = final_text

        try:
            tr = requests.post(api_url, headers={
                "Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
            }, json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "用8个字总结用户的旅行需求，直接输出，不要标点。"},
                    {"role": "user", "content": req.user_query}
                ], "max_tokens": 20,
            }, timeout=15)
            new_title = tr.json()["choices"][0]["message"]["content"].strip()
            if new_title:
                conv.title = new_title
                db.commit()
        except:
            pass

        try:
            mem_resp = requests.post(api_url, headers={
                "Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
            }, json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "从对话中提取用户偏好（如人数、天数、喜欢/不喜欢的类型），输出JSON格式：{\"people\":\"3人\",\"days\":\"1天\",\"likes\":\"美食、历史\"}。如果没有新偏好，输出空{}。"},
                    {"role": "user", "content": req.user_query}
                ], "max_tokens": 100, "temperature": 0,
            }, timeout=15)
            mem_text = mem_resp.json()["choices"][0]["message"]["content"].strip()
            if mem_text and mem_text != "{}":
                try:
                    new_mem = json.loads(mem_text)
                    merged = {**memory, **new_mem}
                    conv.memory = merged
                    db.commit()
                except:
                    pass
        except:
            pass

        # ★ 不再重复推 meta（已在最前面推过了）
        for i in range(0, len(final_text), 5):
            yield f"data: {json.dumps({'type': 'chunk', 'text': final_text[i:i+5]})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)