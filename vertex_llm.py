"""
与 yibelin (doc2doc GeminiTranslator) 对齐的 Vertex AI Gemini 初始化。

凭证优先级：
  1. GOOGLE_CREDENTIALS_ENC + DOC2DOC_SECRETS_KEY（Fernet，与 doc2doc 同一套）
  2. GOOGLE_APPLICATION_CREDENTIALS（明文 JSON 路径）
  3. 同级仓库 doc2doc/src/translationTool/project-*.json（本地开发兜底）

联网：研究员用 Google Search Grounding（Vertex 原生），无需 Custom Search API Key / CX。
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent
try:
    from dotenv import load_dotenv

    load_dotenv(_REPO_ROOT / ".env")
except ImportError:
    pass

_DEFAULT_LOCATION = "us-central1"
_DEFAULT_MODEL = "gemini-2.5-flash"
_ENC_PREFIX = "enc:v1:"


def _fernet(master_key: str):
    from cryptography.fernet import Fernet

    digest = hashlib.sha256(master_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _decrypt_secret(ciphertext: str, master_key: str) -> str:
    raw = ciphertext.strip()
    if raw.startswith(_ENC_PREFIX):
        raw = raw[len(_ENC_PREFIX) :]
    return _fernet(master_key).decrypt(raw.encode("ascii")).decode("utf-8")


def _resolve_credentials_path() -> str:
    """解析服务账号 JSON 路径，逻辑对齐 doc2doc GeminiTranslator._load_credentials_path。"""
    enc = (os.getenv("GOOGLE_CREDENTIALS_ENC") or "").strip()
    master = (os.getenv("DOC2DOC_SECRETS_KEY") or "").strip()
    if enc:
        if not master:
            raise ValueError(
                "GOOGLE_CREDENTIALS_ENC is set but DOC2DOC_SECRETS_KEY is missing"
            )
        json_str = _decrypt_secret(enc, master)
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        tmp.write(json_str)
        tmp.close()
        logger.info("Gemini 凭证已从加密环境变量解密（GOOGLE_CREDENTIALS_ENC）")
        return tmp.name

    env_path = (os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
    if env_path and Path(env_path).is_file():
        logger.info("Gemini 凭证使用 GOOGLE_APPLICATION_CREDENTIALS=%s", env_path)
        return env_path

    sibling = _REPO_ROOT.parent / "doc2doc" / "src" / "translationTool"
    candidates = sorted(sibling.glob("project-*.json")) if sibling.is_dir() else []
    if candidates:
        logger.warning(
            "Gemini 凭证使用 doc2doc 本地文件 %s（仅开发兜底）", candidates[0].name
        )
        return str(candidates[0])

    raise ValueError(
        "找不到 Google 服务账号凭证。\n"
        "推荐：设置 GOOGLE_CREDENTIALS_ENC + DOC2DOC_SECRETS_KEY（与 yibelin 相同）\n"
        "备用：设置 GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json"
    )


def configure_vertex_env() -> tuple[str, str, str]:
    """写入 Vertex 所需环境变量，返回 (project, location, credentials_path)。"""
    credentials_path = _resolve_credentials_path()
    project = (os.getenv("GOOGLE_CLOUD_PROJECT") or "").strip()
    if not project:
        raise ValueError(
            "请设置环境变量 GOOGLE_CLOUD_PROJECT（写入本地 .env，勿提交到仓库）"
        )
    location = (os.getenv("GOOGLE_CLOUD_LOCATION") or _DEFAULT_LOCATION).strip()

    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
    os.environ["GOOGLE_CLOUD_PROJECT"] = project
    os.environ["GOOGLE_CLOUD_LOCATION"] = location
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"

    return project, location, credentials_path


def enable_google_search_grounding(llm: Any) -> Any:
    """
    在 GeminiCompletion 上启用 Google Search Grounding。

    不能把 {"googleSearch": {}} 塞进 CrewAI 的 tools 列表——会被当成普通
    function calling 转换并触发 “function name cannot be empty”。
    正确做法：在 _prepare_generation_config 里注入 types.Tool(google_search=...)。
    """
    if getattr(llm, "_yibelin_google_search_patched", False):
        return llm

    from google.genai import types

    original_prepare = llm._prepare_generation_config

    def prepare_with_grounding(
        system_instruction=None,
        tools=None,
        response_model=None,
    ):
        # 滤掉误塞进列表的 googleSearch 伪 tool dict
        regular_tools = []
        for t in tools or []:
            if isinstance(t, dict) and ("googleSearch" in t or "google_search" in t):
                continue
            regular_tools.append(t)

        # Vertex：Search tool 与 controlled generation（response_schema /
        # response_mime_type=json）不能同时用，故强制关闭结构化输出。
        if response_model is not None:
            logger.warning(
                "忽略 response_model=%s：Google Search Grounding 不支持 controlled generation",
                getattr(response_model, "__name__", type(response_model).__name__),
            )
        config = original_prepare(
            system_instruction=system_instruction,
            tools=regular_tools or None,
            response_model=None,
        )

        grounding = types.Tool(google_search=types.GoogleSearch())
        existing = list(config.tools or [])
        # 避免重复注入
        if not any(getattr(t, "google_search", None) is not None for t in existing):
            existing = [grounding] + existing

        updates = {
            "tools": existing,
            "response_schema": None,
            "response_mime_type": None,
        }
        # GenerateContentConfig 多为 pydantic model，用 model_copy 更新
        if hasattr(config, "model_copy"):
            return config.model_copy(update=updates)
        for key, value in updates.items():
            setattr(config, key, value)
        return config

    llm._prepare_generation_config = prepare_with_grounding  # type: ignore[method-assign]
    llm._yibelin_google_search_patched = True
    logger.info(
        "Enabled Google Search Grounding via GenerateContentConfig on %s",
        type(llm).__name__,
    )
    return llm


def build_gemini_llm(
    model_name: Optional[str] = None,
    temperature: float = 0.7,
):
    """构建与 yibelin 同栈的 CrewAI LLM（Vertex AI + gemini-2.5-flash）。"""
    from crewai import LLM

    project, location, _ = configure_vertex_env()
    model = (model_name or os.getenv("GEMINI_MODEL") or _DEFAULT_MODEL).strip()
    model_id = model if model.startswith("gemini/") else f"gemini/{model}"

    logger.info(
        "CrewAI LLM ready | model=%s | project=%s | location=%s | vertex=true",
        model_id,
        project,
        location,
    )
    return LLM(
        model=model_id,
        temperature=temperature,
        project=project,
        location=location,
    )
