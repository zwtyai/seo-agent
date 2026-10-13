"""
与 yibelin (doc2doc GeminiTranslator) 对齐的 Vertex AI Gemini 初始化。

凭证优先级：
  1. GOOGLE_CREDENTIALS_ENC + DOC2DOC_SECRETS_KEY（Fernet，与 doc2doc 同一套）
  2. GOOGLE_APPLICATION_CREDENTIALS（明文 JSON 路径）
  3. 同级仓库 doc2doc/src/translationTool/project-*.json（本地开发兜底）
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent
try:
    from dotenv import load_dotenv

    load_dotenv(_REPO_ROOT / ".env")
except ImportError:
    pass

# 与 doc2doc GeminiTranslator 默认值保持一致
_DEFAULT_PROJECT = "project-204c4e56-18e3-4ca0-94c"
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

    # 本地开发：复用同级 yibelin/doc2doc 的服务账号文件
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
    """
    写入 Vertex 所需环境变量，返回 (project, location, credentials_path)。
    CrewAI 原生 Gemini SDK 会读取这些变量。
    """
    credentials_path = _resolve_credentials_path()
    project = (os.getenv("GOOGLE_CLOUD_PROJECT") or _DEFAULT_PROJECT).strip()
    location = (os.getenv("GOOGLE_CLOUD_LOCATION") or _DEFAULT_LOCATION).strip()

    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
    os.environ["GOOGLE_CLOUD_PROJECT"] = project
    os.environ["GOOGLE_CLOUD_LOCATION"] = location
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"

    return project, location, credentials_path


def build_gemini_llm(
    model_name: Optional[str] = None,
    temperature: float = 0.7,
):
    """构建与 yibelin 同栈的 CrewAI LLM（Vertex AI + gemini-2.5-flash）。"""
    from crewai import LLM

    project, location, _ = configure_vertex_env()
    model = (model_name or os.getenv("GEMINI_MODEL") or _DEFAULT_MODEL).strip()
    # CrewAI 原生 Google Gen AI：gemini/<model-id>
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
