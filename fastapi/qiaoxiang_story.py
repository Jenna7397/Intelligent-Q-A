from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import uvicorn
import os
import json
import requests
from pydantic import BaseModel
from typing import List, Dict, Any
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# 加载项目根目录 .env（含 API Key、知识库配置）
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_PATH)

# 环境变量配置：对话模型优先 DeepSeek，Kimi 备用
API_KEY = os.getenv("DEEPSEEK_API_KEY") or os.getenv("KIMI_API_KEY") or ""
AI_API_URL = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/chat/completions")
AI_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# 定义数据模型
class StoryRequest(BaseModel):
    query: str

class StoryResponse(BaseModel):
    title: str
    content: str

class APIResponse(BaseModel):
    stories: List[StoryResponse]
    success: bool = True
    message: str = "成功"

# 初始化FastAPI应用
app = FastAPI(
    title="侨乡故事智能问答API",
    description="提供侨乡文化故事的智能问答服务（已接入侨乡知识库RAG）",
    version="2.0.0"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """应用启动时的初始化操作"""
    print("侨乡故事智能问答API服务启动中...")
    if not API_KEY:
        print("警告: DEEPSEEK_API_KEY/KIMI_API_KEY 均未设置，请在 .env 中配置")

@app.get("/", tags=["根路径"])
async def read_root():
    """根路径API，返回服务信息"""
    return {
        "服务": "侨乡故事智能问答API",
        "版本": "2.0.0",
        "状态": "运行中",
        "文档": "/docs"
    }

@app.post("/get_story", response_model=APIResponse, tags=["故事获取"])
async def get_story(request: StoryRequest = Body(...)):
    """
    根据用户查询获取相关的侨乡故事（自动检索知识库注入上下文）
    - **query**: 用户的查询问题
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="查询内容不能为空")
    
    try:
        # 知识库检索：把相关侨乡资料注入上下文（失败时静默降级，不影响原流程）
        context = ""
        try:
            from kb_retriever import search_kb, format_context
            results = search_kb(request.query.strip(), top_k=int(os.getenv("KB_TOP_K", "5")))
            context = format_context(results)
        except Exception as e:
            print(f"[get_story] 知识库检索降级：{e}")

        # 构建AI请求参数
        system_prompt = (
            "你是专业的潮汕侨乡文化讲解员。请根据用户问题生成1个相关故事，故事需包含标题和300字左右的详细内容，"
            "内容需包含历史背景、人物细节或建筑特色，语言生动易懂。请严格以JSON数组格式返回，键名为\"title\"和\"content\""
            "\n\n【严格约束】只能使用下方参考资料中的事实。资料中没有提到的人物、事件、建筑、传说、年代一律不得编造或想象。"
            "如果资料不足以回答问题，就在故事中如实说明「现有资料中暂无详细记录」，不要自行虚构情节。"
        )
        if context:
            system_prompt += (
                "\n\n以下是侨乡知识库检索到的参考资料（必须严格依据这些资料，不得超出资料范围创作）：\n" + context
            )

        payload = {
            "model": AI_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": request.query.strip()
                }
            ],
            "temperature": 0.3,
            "max_tokens": 1500,
            "n": 1
        }
        
        # 发送请求到AI服务
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}"
        }
        
        response = requests.post(
            AI_API_URL,
            data=json.dumps(payload),
            headers=headers,
            timeout=60
        )
        
        # 处理AI响应
        if response.status_code != 200:
            error_msg = f"AI服务请求失败，状态码: {response.status_code}"
            if response.text:
                try:
                    error_data = response.json()
                    error_msg += f", 错误信息: {error_data.get('error', {}).get('message', '无详细信息')}"
                except:
                    error_msg += f", 原始响应: {response.text[:100]}"
            raise HTTPException(status_code=500, detail=error_msg)
        
        ai_data = response.json()
        if not ai_data.get("choices") or not ai_data["choices"][0].get("message", {}).get("content"):
            raise HTTPException(status_code=500, detail="AI服务返回格式异常，未获取到有效内容")
        
        # 解析AI返回的故事内容
        try:
            story_content = ai_data["choices"][0]["message"]["content"]
            # 剥离可能的 Markdown 代码块（```json ... ```），容错解析
            parsed_text = story_content.strip()
            if parsed_text.startswith("```"):
                lines = parsed_text.splitlines()
                if lines and lines[0].strip().startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                parsed_text = "\n".join(lines).strip()
            stories = json.loads(parsed_text)
            
            # 确保返回的是数组
            if not isinstance(stories, list):
                stories = [stories]
                
            # 验证每个故事的格式
            validated_stories = []
            for story in stories[:1]:  # 只取第一个故事
                if isinstance(story, dict) and "title" in story and "content" in story:
                    validated_stories.append(StoryResponse(
                        title=story["title"],
                        content=story["content"]
                    ))
            
            if not validated_stories:
                raise HTTPException(status_code=500, detail="AI返回的故事格式不符合要求")
                
            return APIResponse(stories=validated_stories)
            
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=500, detail=f"解析AI响应失败: {str(e)}, 原始内容: {story_content[:200]}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"处理AI响应失败: {str(e)}")
            
    except requests.Timeout:
        raise HTTPException(status_code=504, detail="AI服务请求超时")
    except requests.ConnectionError:
        raise HTTPException(status_code=503, detail="无法连接到AI服务")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取故事时发生错误: {str(e)}")

@app.post("/get_story_stream", tags=["故事获取（流式）"])
async def get_story_stream(request: StoryRequest = Body(...)):
    """
    流式获取潮汕侨乡故事（SSE）。边生成边推送，前端可边显示边合成语音。
    第一行是标题，后续是正文。
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="查询内容不能为空")

    # 知识库检索
    context = ""
    try:
        from kb_retriever import search_kb, format_context
        results = search_kb(request.query.strip(), top_k=int(os.getenv("KB_TOP_K", "5")))
        context = format_context(results)
    except Exception as e:
        print(f"[get_story_stream] 知识库检索降级：{e}")

    system_prompt = (
        "你是专业的潮汕侨乡文化讲解员。请根据用户问题，严格根据【参考资料】直接介绍用户询问的人物、事件或地点。"
        "第一行只输出故事标题（不要加书名号、引号或序号），从第二行开始输出正文，输出介绍性的文字，约300字。"
        "正文需包含历史背景、人物细节或建筑特色，语言生动易懂。"
        "\n\n【严格约束】只能使用下方参考资料中的事实。资料中没有提到的人物、事件、建筑、传说、年代一律不得编造或想象。"
        "如果资料不足以回答问题，就在故事中如实说明「现有资料中暂无详细记录」，不要自行虚构情节。"
    )
    if context:
        system_prompt += (
            "\n\n以下是侨乡知识库检索到的参考资料（必须严格依据这些资料，不得超出资料范围创作）：\n" + context
        )

    payload = {
        "model": AI_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": request.query.strip()}
        ],
        "temperature": 0.3,
        "max_tokens": 1500,
        "stream": True
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }

    def generate():
        try:
            with requests.post(
                AI_API_URL,
                data=json.dumps(payload),
                headers=headers,
                timeout=60,
                stream=True
            ) as r:
                if r.status_code != 200:
                    yield f'data: {json.dumps({"error": f"AI服务错误: {r.status_code}"}, ensure_ascii=False)}\n\n'
                    return
                for line in r.iter_lines():
                    if not line:
                        continue
                    line = line.decode("utf-8")
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        yield 'data: [DONE]\n\n'
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0].get("delta", {}).get("content", "")
                        if delta:
                            yield f'data: {json.dumps({"delta": delta}, ensure_ascii=False)}\n\n'
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            yield f'data: {json.dumps({"error": str(e)}, ensure_ascii=False)}\n\n'

    return StreamingResponse(generate(), media_type="text/event-stream")

@app.get("/health", tags=["健康检查"])
async def health_check():
    """健康检查API，用于监控服务状态"""
    return {
        "status": "ok",
        "time": datetime.now().isoformat(),
        "api_key_configured": bool(API_KEY),
        "model": AI_MODEL
    }

# 辅助函数：提取关键词
def extract_keywords(text: str) -> List[str]:
    """从文本中提取关键词"""
    import re
    # 去除标点符号
    text = re.sub(r'[^\w\s]', '', text)
    # 分割单词
    words = text.split()
    # 过滤长度小于2的单词，并取前5个
    return [word for word in words if len(word) > 1][:5]

# 主函数：启动服务
if __name__ == "__main__":
    uvicorn.run(
        "qiaoxiang_story:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 8000)),
        reload=os.getenv("DEBUG", "false").lower() == "true",
        log_level="debug" if os.getenv("DEBUG", "false").lower() == "true" else "info"
    )
