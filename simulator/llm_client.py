# -*- coding: utf-8 -*-
"""
模拟器统一 LLM 调用：所有 NPC、学生、评估器等共用同一套 HTTP 调用与默认配置。
"""
import json
from typing import List, Dict, Any

import requests


def get_simulator_default_config() -> dict:
    """从 config 读取模拟器用默认配置（api_url, api_key, model）。"""
    from config import DEEPSEEK_CHAT_URL, DEEPSEEK_API_KEY, DEEPSEEK_MODEL
    return {
        "api_url": DEEPSEEK_CHAT_URL,
        "api_key": DEEPSEEK_API_KEY or "",
        "model": DEEPSEEK_MODEL,
    }


def call_chat_completion(
    api_url: str,
    api_key: str,
    model: str,
    messages: List[Dict[str, str]],
    *,
    max_tokens: int = 400,
    temperature: float = 0.7,
    service_code: str = "",
    timeout: int = 60,
) -> str:
    """
    调用 OpenAI 兼容的 Chat Completions API，返回单条回复内容。

    Args:
        api_url: 完整 URL（如 https://api.deepseek.com/chat/completions）
        api_key: API Key
        model: 模型名
        messages: 消息列表 [{"role": "system"|"user"|"assistant", "content": "..."}]
        max_tokens: 最大生成 token 数
        temperature: 温度
        service_code: 可选请求头 serviceCode
        timeout: 请求超时秒数

    Returns:
        回复文本（choices[0].message.content 或兼容字段）

    Raises:
        RuntimeError: 请求失败或响应无法解析
    """
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if service_code:
        headers["serviceCode"] = service_code

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }

    response = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
    response.raise_for_status()
    result = response.json()

    if "choices" in result and len(result["choices"]) > 0:
        return result["choices"][0]["message"]["content"]
    if "content" in result:
        return result["content"]
    if "response" in result:
        return result["response"]
    raise ValueError(f"无法解析 API 响应: {result}")
