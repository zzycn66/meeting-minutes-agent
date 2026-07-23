# -*- coding: utf-8 -*-
"""会议纪要智能体 - 主应用入口"""
import os
import sys
import logging

_backend_dir = os.path.dirname(os.path.abspath(__file__))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

# 提前加载 .env 并设置 HF_ENDPOINT
# 必须在导入 transformers 之前完成，因为 huggingface_hub 在导入时
# 会通过 os.environ.get("HF_ENDPOINT") 缓存该值，后续修改无效
_dotenv_path = os.path.join(_backend_dir, ".env")
if os.path.exists(_dotenv_path):
    try:
        from dotenv import load_dotenv
        load_dotenv(_dotenv_path)
    except ImportError:
        pass

# 确保 HF_ENDPOINT 在 huggingface_hub 导入前已设置
if "HF_ENDPOINT" not in os.environ:
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

# 预加载 transformers/torch（避免 uvicorn 上下文中的延迟 ImportError）
try:
    from transformers import AutoTokenizer, AutoModelForCausalLM
    import torch
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    logging.getLogger(__name__).info("transformers/torch 预加载成功")
except ImportError as e:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    logging.getLogger(__name__).warning(f"transformers/torch 预加载失败: {e}")

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.models import Meeting, MeetingMinutes, ActionItem, User, MeetingTemplate
from app.database import engine, Base
from app.routes import meetings, minutes, export, auth, templates, websocket, audio, public
from app.routes.qa import qa_router
from config import ALLOWED_ORIGINS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

FRONTEND_DIR = os.path.join(_backend_dir, "frontend")

app = FastAPI(
    title="会议纪要智能体",
    description="智能会议纪要助手 - 自动转写、提取、生成结构化会议纪要",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meetings.router)
app.include_router(minutes.router)
app.include_router(export.router)
app.include_router(auth.router)
app.include_router(templates.router)
app.include_router(websocket.router)
app.include_router(audio.audio_router)
app.include_router(public.router)
app.include_router(qa_router)

if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.on_event("startup")
async def startup():
    Base.metadata.create_all(bind=engine)
    logger.info("=" * 50)
    logger.info("  会议纪要智能体 (Meeting Minutes Agent)")
    logger.info("  API服务已启动: http://localhost:8000")
    logger.info("  API文档: http://localhost:8000/docs")
    logger.info("=" * 50)

    import threading
    def _preload():
        logger.info("Pre-loading faster-whisper model...")
        from app.services.speech_service import _get_faster_whisper_model
        m = _get_faster_whisper_model()
        logger.info("Model pre-loaded: %s", "OK" if m else "FAILED")
    threading.Thread(target=_preload, daemon=True).start()


@app.get("/")
async def index():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"})
    return {"message": "会议纪要智能体API服务运行中", "docs": "/docs"}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "Meeting Minutes Agent"}


if __name__ == "__main__":
    import uvicorn
    from config import HOST, PORT
    Base.metadata.create_all(bind=engine)
    uvicorn.run("main:app", host=HOST, port=PORT, reload=False)
