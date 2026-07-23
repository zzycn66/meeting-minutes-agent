# -*- coding: utf-8 -*-
"""会议相关API路由"""
import os
import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from datetime import datetime

from app.database import get_db
from app.models import Meeting, MeetingMinutes, ActionItem, User
from app.schemas import MeetingCreate, MeetingUpdate, MeetingResponse, MinutesResponse, ActionItemResponse, APIResponse, PYDANTIC_V2, to_response
from app.services.meeting_service import meeting_service
from app.routes.auth import require_user
from config import UPLOAD_DIR

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/meetings", tags=["会议管理"])


@router.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...), user: User = Depends(require_user)):
    """上传音频文件"""
    logger.info("/upload-audio called, filename=%s", file.filename)
    result = await meeting_service.save_audio(file)
    if not result["success"]:
        return APIResponse(success=False, message=result["message"])
    return APIResponse(success=True, message=result["message"], data=result["data"])


@router.post("/recognize")
async def recognize_speech(filepath: str = Form(""), text: str = Form(""), asr_engine: str = Form(""), user: User = Depends(require_user)):
    """语音识别/文本处理"""
    engine_label = asr_engine if asr_engine else "auto"
    logger.info("/recognize | engine=%s | filepath=%s | text_len=%d", engine_label, filepath, len(text) if text else 0)

    result = meeting_service.recognize(filepath, text, asr_engine)
    if not result["success"]:
        logger.error("FAILED: %s", result['message'])
        return APIResponse(success=False, message=result["message"])

    return APIResponse(success=True, message=result["message"], data={"text": result["text"]})


@router.post("")
async def create_meeting(data: MeetingCreate, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """创建会议记录"""
    result = meeting_service.create_meeting(data, db)
    if result.get("success") and result.get("data", {}).get("id"):
        meeting = db.query(Meeting).filter(Meeting.id == result["data"]["id"]).first()
        if meeting:
            meeting.created_by = user.id
            db.commit()
    return APIResponse(**result)


@router.get("")
async def list_meetings(page: int = 1, size: int = 20, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """获取会议列表（子查询合并 count + data）"""
    from sqlalchemy import func, select

    # 合并 count 和 data 为一次查询
    subq = (
        db.query(
            Meeting,
            func.count().over().label("total_count"),
        )
        .filter(Meeting.created_by == user.id)
        .order_by(Meeting.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    total = subq[0][1] if subq else 0
    meetings = [row[0] for row in subq]

    return APIResponse(success=True, data={
        "total": total, "page": page, "size": size,
        "items": [to_response(MeetingResponse, m) for m in meetings],
    })


@router.get("/{meeting_id}")
async def get_meeting(meeting_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """获取会议详情"""
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id, Meeting.created_by == user.id).first()
    if not meeting:
        return APIResponse(success=False, message="会议记录不存在")
    return APIResponse(success=True, data={"meeting": to_response(MeetingResponse, meeting)})


@router.put("/{meeting_id}")
async def update_meeting(meeting_id: int, data: MeetingUpdate, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """更新会议记录"""
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id, Meeting.created_by == user.id).first()
    if not meeting:
        return APIResponse(success=False, message="会议记录不存在")
    update_data = data.model_dump(exclude_unset=True) if PYDANTIC_V2 else data.dict(exclude_unset=True)
    if "meeting_date" in update_data and update_data["meeting_date"]:
        update_data["meeting_date"] = datetime.strptime(update_data["meeting_date"], "%Y-%m-%d")
    for k, v in update_data.items():
        setattr(meeting, k, v)
    db.commit()
    return APIResponse(success=True, message="更新成功")


@router.delete("/{meeting_id}")
async def delete_meeting(meeting_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """删除会议记录"""
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id, Meeting.created_by == user.id).first()
    if not meeting:
        return APIResponse(success=False, message="会议记录不存在")
    db.delete(meeting)
    db.commit()
    return APIResponse(success=True, message="删除成功")


@router.patch("/{meeting_id}/toggle-public")
async def toggle_public(meeting_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """切换会议公开状态"""
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id, Meeting.created_by == user.id).first()
    if not meeting:
        return APIResponse(success=False, message="会议记录不存在")
    meeting.is_public = not meeting.is_public
    db.commit()
    return APIResponse(success=True, message="已切换公开状态", data={"is_public": meeting.is_public})
