from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import os
import json
import uuid
import base64
import requests
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv

# 加载项目根目录 .env（含 API Key）
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_PATH)

app = FastAPI(
    title="侨乡语音讲解合成API",
    description="基于火山引擎豆包语音（V3）的文字转语音服务，为侨乡故事/景点提供语音讲解",
    version="1.0.0"
)

# 配置CORS，允许前端请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 火山引擎豆包语音配置（从根目录 .env 读取）
VOLC_API_KEY = os.getenv("VOLC_API_KEY", "")
VOLC_RESOURCE_ID = os.getenv("VOLC_RESOURCE_ID", "seed-tts-2.0")
VOLC_SPEAKER = os.getenv("VOLC_SPEAKER", "zh_female_vv_uranus_bigtts")
VOLC_TTS_URL = os.getenv("VOLC_TTS_URL", "https://openspeech.bytedance.com/api/v3/tts/unidirectional")

# 请求/响应数据模型
class TTSRequest(BaseModel):
    text: str                      # 要合成的讲解文本
    voice: Optional[str] = None    # 可选：覆盖默认音色
    speech_rate: int = 0           # 语速 [-50, 100]，0 为正常语速
    loudness_rate: int = 0         # 音量 [-50, 100]，0 为正常音量

class TTSResponse(BaseModel):
    success: bool = True
    audio_base64: str = ""         # mp3 音频的 base64，前端可直接播放
    format: str = "mp3"
    duration_ms: Optional[int] = None
    error: str = None
    speaker: str = ""


def synthesize_speech(text: str, speaker: str, speech_rate: int = 0, loudness_rate: int = 0) -> bytes:
    """调用火山引擎豆包语音 V3 单向流式接口，返回 mp3 二进制音频"""
    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="text 不能为空")

    if not VOLC_API_KEY:
        raise HTTPException(status_code=503, detail="未配置 VOLC_API_KEY，请在项目根目录 .env 中填入火山引擎 API Key")

    payload = {
        "req_params": {
            "text": text.strip(),
            "speaker": speaker,
            "audio_params": {
                "format": "mp3",
                "sample_rate": 24000
            },
            "disable_markdown_filter": True,
            "disable_emoji_filter": True
        }
    }
    if speech_rate:
        payload["req_params"]["audio_params"]["speech_rate"] = speech_rate
    if loudness_rate:
        payload["req_params"]["audio_params"]["loudness_rate"] = loudness_rate

    headers = {
        "Content-Type": "application/json",
        "X-Api-Key": VOLC_API_KEY,
        "X-Api-Resource-Id": VOLC_RESOURCE_ID,
        "X-Api-Request-Id": str(uuid.uuid4()),
        "Connection": "keep-alive"
    }

    try:
        # V3 接口为 HTTP Chunked 流式返回：每个 chunk 是一行 JSON，data 为 base64 音频片段
        with requests.post(VOLC_TTS_URL, headers=headers, json=payload, stream=True, timeout=120) as resp:
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"语音服务响应异常({resp.status_code}): {resp.text[:200]}")

            audio_parts = []
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    # 跳过非 JSON 的边界行
                    continue
                code = chunk.get("code", -1)
                # V3 接口成功码：0（首包/元数据）或 20000000（OK）；其余为错误码
                if code not in (0, 20000000):
                    raise HTTPException(status_code=502, detail=f"语音合成失败({code}): {chunk.get('message', '未知错误')}")
                data = chunk.get("data")
                if data:
                    audio_parts.append(base64.b64decode(data))

            audio = b"".join(audio_parts)
            if not audio:
                raise HTTPException(status_code=502, detail="语音服务未返回音频数据")
            return audio

    except HTTPException:
        raise
    except requests.Timeout:
        raise HTTPException(status_code=504, detail="语音服务请求超时")
    except requests.ConnectionError:
        raise HTTPException(status_code=503, detail="无法连接到语音服务")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"语音合成失败: {str(e)}")


@app.post("/api/tts", response_model=TTSResponse, tags=["语音讲解"])
async def text_to_speech(request: TTSRequest):
    """文字转语音：输入讲解文本，返回 mp3 音频（base64）"""
    speaker = request.voice or VOLC_SPEAKER
    try:
        audio = synthesize_speech(request.text, speaker, request.speech_rate, request.loudness_rate)
        return TTSResponse(
            success=True,
            audio_base64=base64.b64encode(audio).decode("ascii"),
            format="mp3",
            speaker=speaker
        )
    except HTTPException as e:
        return TTSResponse(success=False, error=e.detail, speaker=speaker)


@app.get("/api/tts/health", tags=["语音讲解"])
async def health_check():
    """检查语音服务配置状态"""
    return {
        "status": "ok",
        "configured": bool(VOLC_API_KEY),
        "speaker": VOLC_SPEAKER,
        "resource_id": VOLC_RESOURCE_ID
    }


@app.get("/", tags=["根路径"])
async def read_root():
    return {
        "服务": "侨乡语音讲解合成API",
        "版本": "1.0.0",
        "文档": "/docs",
        "说明": "POST /api/tts 传入 text 获取语音讲解"
    }


if __name__ == "__main__":
    uvicorn.run("tts:app", host="0.0.0.0", port=8002)
