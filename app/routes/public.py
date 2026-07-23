# -*- coding: utf-8 -*-
"""公开文档API路由 - 无需登录"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Meeting, MeetingMinutes, ActionItem
from app.schemas import APIResponse, MeetingResponse, MinutesResponse, ActionItemResponse, to_response, build_meeting_data
from app.services.minutes_service import minutes_generator

router = APIRouter(prefix="/api/public", tags=["公开文档"])


@router.get("/meetings")
async def list_public_meetings(page: int = 1, size: int = 20, db: Session = Depends(get_db)):
    """获取公开会议列表"""
    from sqlalchemy import func
    subq = (
        db.query(Meeting, func.count().over().label("total_count"))
        .filter(Meeting.is_public == True, Meeting.status == "completed")
        .order_by(Meeting.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    total = subq[0][1] if subq else 0
    meetings = [row[0] for row in subq]

    items = []
    for m in meetings:
        items.append({
            "id": m.id,
            "title": m.title,
            "meeting_date": m.meeting_date.isoformat() if m.meeting_date else None,
            "participants": m.participants,
            "created_at": m.created_at.isoformat() if m.created_at else None,
            "created_by": m.created_by,
        })

    return APIResponse(success=True, data={
        "total": total, "page": page, "size": size,
        "items": items,
    })


@router.get("/meetings/{meeting_id}")
async def get_public_meeting(meeting_id: int, db: Session = Depends(get_db)):
    """获取公开会议详情（不含原文）"""
    meeting = (
        db.query(Meeting)
        .options(
            joinedload(Meeting.minutes),
            joinedload(Meeting.action_items),
        )
        .filter(Meeting.id == meeting_id, Meeting.is_public == True)
        .first()
    )
    if not meeting:
        return APIResponse(success=False, message="会议记录不存在或未公开")

    minutes = meeting.minutes
    action_items = meeting.action_items

    if minutes and minutes.markdown and minutes.html:
        markdown = minutes.markdown
        html = minutes.html
    else:
        meeting_data = build_meeting_data(meeting, minutes, action_items)
        markdown = minutes_generator.generate_markdown(meeting_data)
        html = minutes_generator.generate_html(meeting_data)

    return APIResponse(success=True, data={
        "meeting": {
            "id": meeting.id,
            "title": meeting.title,
            "meeting_date": meeting.meeting_date.isoformat() if meeting.meeting_date else None,
            "participants": meeting.participants,
            "created_by": meeting.created_by,
        },
        "markdown": markdown,
        "html": html,
        "action_items": [to_response(ActionItemResponse, a) for a in action_items] if action_items else [],
    })
