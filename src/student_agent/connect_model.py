from __future__ import annotations

import json
import os
from typing import Any

import httpx2


async def call_nvidia_llm(
    prompt: str,
    system_prompt: str = (
        "Bạn là trợ lý phân tích khiếu nại thương mại điện tử chuyên nghiệp. "
        "Hãy trả về kết quả dưới dạng JSON."
    ),
    temperature: float = 0.2,
) -> dict[str, Any]:
    """Gọi model qua NVIDIA NIM API."""
    api_key = os.getenv("LLM_API_KEY", "").strip()
    model = os.getenv("LLM_MODEL", "meta/llama-3.2-11b-vision-instruct").strip()
    base_url = os.getenv("LLM_BASE_URL", "https://integrate.api.nvidia.com/v1").rstrip("/")

    if not api_key:
        return {}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": 512,
    }

    try:
        async with httpx2.AsyncClient(timeout=25.0) as client:
            resp = await client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]
                # Thử parse JSON nếu model trả về JSON string
                try:
                    return json.loads(content)
                except Exception:
                    return {"text": content}
    except Exception as exc:
        # Fallback an toàn nếu mạng lỗi, không làm gián đoạn pipeline thi
        return {"error": str(exc)}
    return {}