# -*- coding: utf-8 -*-
"""导出API路由"""
import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi.responses import FileResponse

from app.database import get_db
from app.models import Meeting, MeetingMinutes, ActionItem, User
from app.schemas import APIResponse, build_meeting_data
from app.services.minutes_service import minutes_generator
from app.routes.auth import require_user
from config import UPLOAD_DIR

router = APIRouter(prefix="/api/export", tags=["导出"])


@router.get("/docx/{meeting_id}")
async def export_docx(meeting_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """导出会议纪要为Word文档"""
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id, Meeting.created_by == user.id).first()
    if not meeting:
        return APIResponse(success=False, message="会议记录不存在")

    minutes = db.query(MeetingMinutes).filter(MeetingMinutes.meeting_id == meeting_id).first()
    action_items = db.query(ActionItem).filter(ActionItem.meeting_id == meeting_id).all()

    meeting_data = build_meeting_data(meeting, minutes, action_items)

    output_dir = os.path.join(UPLOAD_DIR, "exports")
    os.makedirs(output_dir, exist_ok=True)
    safe_title = "".join(c for c in meeting.title if c.isalnum() or c in (' ', '_', '-')).strip()
    output_path = os.path.join(output_dir, f"{safe_title}_会议纪要.docx")

    try:
        minutes_generator.export_to_docx(meeting_data, output_path)
        return FileResponse(
            output_path,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=f"{safe_title}_会议纪要.docx",
        )
    except ImportError:
        return APIResponse(success=False, message="导出功能需要python-docx库")
    except Exception as e:
        return APIResponse(success=False, message=f"导出失败: {str(e)}")


@router.get("/markdown/{meeting_id}")
async def export_markdown(meeting_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """导出会议纪要为Markdown文本"""
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id, Meeting.created_by == user.id).first()
    if not meeting:
        return APIResponse(success=False, message="会议记录不存在")

    minutes = db.query(MeetingMinutes).filter(MeetingMinutes.meeting_id == meeting_id).first()
    action_items = db.query(ActionItem).filter(ActionItem.meeting_id == meeting_id).all()

    if not minutes:
        return APIResponse(success=False, message="请先生成会议纪要")

    meeting_data = build_meeting_data(meeting, minutes, action_items)

    markdown = minutes_generator.generate_markdown(meeting_data)
    return APIResponse(success=True, data={"markdown": markdown})
