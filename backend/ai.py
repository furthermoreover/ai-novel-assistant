# -*- coding: utf-8 -*-
"""AI 能力封装：智谱 embedding + 多厂商对话生成"""
import httpx
from config import (
    ZHIPU_API_KEY, EMBEDDING_API_URL, EMBEDDING_MODEL, EMBEDDING_DIM,
    CHAT_API_URL, CHAT_API_KEY, WRITING_MODEL, SUMMARIZE_MODEL,
)

HEADERS = {
    "Authorization": f"Bearer {ZHIPU_API_KEY}",
    "Content-Type": "application/json",
}

CHAT_HEADERS = {
    "Authorization": f"Bearer {CHAT_API_KEY}",
    "Content-Type": "application/json",
}


def embed_text(text: str) -> list[float]:
    """调用智谱 embedding-3 生成向量（1024 维）"""
    if not ZHIPU_API_KEY:
        raise RuntimeError("未配置 ZHIPU_API_KEY，请在 .env 中填写")
    payload = {
        "model": EMBEDDING_MODEL,
        "input": text[:8000],
        "dimensions": EMBEDDING_DIM,
    }
    with httpx.Client(timeout=60) as client:
        resp = client.post(EMBEDDING_API_URL, json=payload, headers=HEADERS)
        resp.raise_for_status()
        data = resp.json()
    emb = data["data"][0]["embedding"]
    return emb


def chat_completion(messages: list[dict], model: str = WRITING_MODEL,
                    temperature: float = 0.8, max_tokens: int = 4096,
                    stream: bool = False):
    """调用对话接口（OpenAI 兼容：智谱/千问等），支持流式"""
    if not CHAT_API_KEY:
        raise RuntimeError("未配置 CHAT_API_KEY / ZHIPU_API_KEY，请在 .env 中填写")
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream,
    }
    if stream:
        # 流式：返回迭代器
        client = httpx.Client(timeout=300)
        req = client.build_request("POST", CHAT_API_URL, json=payload, headers=CHAT_HEADERS)
        resp = client.send(req, stream=True)
        resp.raise_for_status()
        return _iter_stream(resp, client)
    else:
        with httpx.Client(timeout=300) as client:
            resp = client.post(CHAT_API_URL, json=payload, headers=CHAT_HEADERS)
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]["message"]["content"]


def _iter_stream(resp, client):
    """解析 SSE 流式响应，产出文本增量"""
    try:
        for line in resp.iter_lines():
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            import json
            try:
                obj = json.loads(data)
                delta = obj["choices"][0]["delta"].get("content", "")
                if delta:
                    yield delta
            except Exception:
                continue
    finally:
        resp.close()
        client.close()
