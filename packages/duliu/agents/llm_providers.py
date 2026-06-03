"""LLM provider registry (OpenAI-compatible chat/completions)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

LlmProviderId = Literal["openai", "deepseek", "qwen", "glm"]

PROVIDER_IDS: tuple[str, ...] = ("openai", "deepseek", "qwen", "glm")


@dataclass(frozen=True)
class LlmProviderSpec:
    id: str
    label: str
    base_url: str
    default_model: str
    api_key_secret: str
    model_secret: str
    env_api_key: str
    env_model: str


PROVIDERS: dict[str, LlmProviderSpec] = {
    "openai": LlmProviderSpec(
        id="openai",
        label="OpenAI",
        base_url="https://api.openai.com/v1/chat/completions",
        default_model="gpt-4o-mini",
        api_key_secret="openai_api_key",
        model_secret="llm_openai_model",
        env_api_key="OPENAI_API_KEY",
        env_model="DULIU_OPENAI_MODEL",
    ),
    "deepseek": LlmProviderSpec(
        id="deepseek",
        label="DeepSeek",
        base_url="https://api.deepseek.com/v1/chat/completions",
        default_model="deepseek-chat",
        api_key_secret="deepseek_api_key",
        model_secret="llm_deepseek_model",
        env_api_key="DULIU_DEEPSEEK_API_KEY",
        env_model="DULIU_DEEPSEEK_MODEL",
    ),
    "qwen": LlmProviderSpec(
        id="qwen",
        label="通义千问 (Qwen)",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        default_model="qwen-plus",
        api_key_secret="qwen_api_key",
        model_secret="llm_qwen_model",
        env_api_key="DULIU_QWEN_API_KEY",
        env_model="DULIU_QWEN_MODEL",
    ),
    "glm": LlmProviderSpec(
        id="glm",
        label="智谱 GLM",
        base_url="https://open.bigmodel.cn/api/paas/v4/chat/completions",
        default_model="glm-4-flash",
        api_key_secret="glm_api_key",
        model_secret="llm_glm_model",
        env_api_key="DULIU_GLM_API_KEY",
        env_model="DULIU_GLM_MODEL",
    ),
}

ACTIVE_PROVIDER_SECRET = "llm_active_provider"
