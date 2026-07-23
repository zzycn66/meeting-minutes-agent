# -*- coding: utf-8 -*-
"""Pydantic数据模型 - 兼容 Pydantic v1 和 v2"""
from typing import Optional, List, Union, Any
from datetime import datetime

try:
    from pydantic import BaseModel, Field, ConfigDict
    PYDANTIC_V2 = True
except ImportError:
    from pydantic import BaseModel, Field
    PYDANTIC_V2 = False

class MeetingCreate(BaseModel):
    title: Optional[str] = Field(None, description="会议标题（不填则自动生成）")
    meeting_name: Optional[str] = Field(None, description="会议名称/类型（不填则自动识别）")
    meeting_date: Optional[str] = None
    duration: Optional[str] = None
    participants: Optional[str] = None
    input_type: str = "text"
    raw_text: Optional[str] = None
    is_public: bool = False

class MeetingUpdate(BaseModel):
    title: Optional[str] = None
    meeting_date: Optional[str] = None
    duration: Optional[str] = None
    participants: Optional[str] = None
    raw_text: Optional[str] = None

class MeetingResponse(BaseModel):
    id: int
    title: str
    meeting_date: Optional[datetime] = None
    duration: Optional[str] = None
    participants: Optional[str] = None
    input_type: str
    raw_text: Optional[str] = None
    status: str
    is_public: bool = False
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    if PYDANTIC_V2:
        model_config = ConfigDict(from_attributes=True)
    else:
        class Config:
            orm_mode = True

class MinutesResponse(BaseModel):
    id: int
    meeting_id: int
    topic: Optional[str] = None
    overview: Optional[str] = None
    discussion_points: Optional[str] = None
    key_decisions: Optional[str] = None
    unresolved_issues: Optional[str] = None
    summary: Optional[str] = None
    created_at: Optional[datetime] = None

    if PYDANTIC_V2:
        model_config = ConfigDict(from_attributes=True)
    else:
        class Config:
            orm_mode = True

class ActionItemCreate(BaseModel):
    content: str
    responsible_person: Optional[str] = None
    deadline: Optional[str] = None
    priority: str = "medium"

class ActionItemUpdate(BaseModel):
    content: Optional[str] = None
    responsible_person: Optional[str] = None
    deadline: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None

class ActionItemResponse(BaseModel):
    id: int
    meeting_id: int
    content: str
    responsible_person: Optional[str] = None
    deadline: Optional[str] = None
    priority: str
    status: str
    created_at: Optional[datetime] = None

    if PYDANTIC_V2:
        model_config = ConfigDict(from_attributes=True)
    else:
        class Config:
            orm_mode = True

class APIResponse(BaseModel):
    success: bool
    message: str = ""
    data: Optional[Any] = None


def to_response(model_class, obj):
    """Pydantic v1/v2 兼容序列化"""
    if PYDANTIC_V2:
        return model_class.model_validate(obj).model_dump()
    else:
        return model_class.from_orm(obj).dict()


def serialize_action_items(action_items) -> list:
    """统一的行动项序列化"""
    return [
        {
            "content": a.content,
            "responsible_person": a.responsible_person or "",
            "deadline": a.deadline or "",
            "priority": a.priority or "medium",
        }
        for a in action_items
    ]


def build_meeting_data(meeting, minutes=None, action_items=None, nlp_result=None) -> dict:
    """统一的 meeting_data 构建函数，消除 minutes.py / export.py 中的重复代码"""
    data = {
        "title": meeting.title or "会议纪要",
        "meeting_date": meeting.meeting_date.strftime("%Y年%m月%d日") if meeting.meeting_date else "",
        "participants": meeting.participants or "",
    }
    if nlp_result:
        data.update(nlp_result)
    elif minutes:
        data.update({
            "topic": minutes.topic or "",
            "overview": minutes.overview or "",
            "discussion_points": minutes.discussion_points or "",
            "key_decisions": minutes.key_decisions or "",
            "unresolved_issues": minutes.unresolved_issues or "",
            "summary": minutes.summary or "",
        })
    if action_items is not None:
        data["action_items"] = serialize_action_items(action_items)
    return data
