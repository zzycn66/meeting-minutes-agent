# -*- coding: utf-8 -*-
"""音频处理API路由"""
import os
import logging
from fastapi import APIRouter, Depends, Form

from app.schemas import APIResponse
from app.models import User
from app.audio_processor import AudioProcessor
from app.routes.auth import require_user

logger = logging.getLogger(__name__)
audio_router = APIRouter(prefix="/api/audio", tags=["音频处理"])

audio_processor = AudioProcessor()


@audio_router.post("/enhance")
async def enhance_audio(
    filepath: str = Form(..., description="音频文件路径"),
    output_path: str = Form("", description="输出路径（可选）"),
    user: User = Depends(require_user),
):
    """增强音频：降噪 + 音量标准化"""
    logger.info(f"/api/audio/enhance | filepath={filepath}")

    if not filepath:
        return APIResponse(success=False, message="文件路径不能为空")

    if not os.path.exists(filepath):
        return APIResponse(success=False, message=f"文件不存在: {filepath}")

    if not output_path:
        base, ext = os.path.splitext(filepath)
        output_path = f"{base}_enhanced{ext}"

    result = audio_processor.enhance_audio(filepath, output_path)

    if result["success"]:
        return APIResponse(
            success=True, 
            message=result["message"],
            data={"output_path": result["output_path"]}
        )
    else:
        return APIResponse(success=False, message=result["message"])
