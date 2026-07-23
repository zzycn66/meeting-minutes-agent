# -*- coding: utf-8 -*-
"""项目配置文件"""
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 数据库配置
DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'meeting_agent.db')}"

# MiMo ASR 配置
MIMO_API_KEY = os.environ.get("MIMO_API_KEY", "")
MIMO_ASR_BASE_URL = os.environ.get("MIMO_ASR_BASE_URL", "https://api.xiaomimimo.com/v1")

# DeepSeek API 配置
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

# 文件上传配置
UPLOAD_DIR = os.path.join(os.path.dirname(BASE_DIR), "frontend", "uploads")
MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100MB
ALLOWED_AUDIO_EXTENSIONS = {"mp3", "wav", "m4a", "aac", "wma", "ogg", "flac", "webm"}

# 服务配置
HOST = "0.0.0.0"
PORT = 8000

# Qwen3 本地模型配置（HuggingFace 模型 ID 或本地路径）
LOCAL_MODEL_NAME = os.environ.get("LOCAL_MODEL_NAME", "Qwen/Qwen3-0.6B")
LOCAL_MODEL_CACHE = os.environ.get("LOCAL_MODEL_CACHE", "")
LOCAL_MODEL_DEVICE = os.environ.get("LOCAL_MODEL_DEVICE", "cpu")
LOCAL_MODEL_MAX_TOKENS = int(os.environ.get("LOCAL_MODEL_MAX_TOKENS", "1024"))

# Whisper 语音识别模型配置（tiny/base/small/medium/large-v3）
# medium: 准确率与资源需求的平衡点，推荐大多数用户使用
WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL_SIZE", "medium")

HF_ENDPOINT = os.environ.get("HF_ENDPOINT", "https://hf-mirror.com")

# CORS 配置
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "http://localhost:8000").split(",")

