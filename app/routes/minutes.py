# -*- coding: utf-8 -*-
"""纪要生成与行动项API路由"""
import os
import asyncio
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from app.database import get_db
from app.models import Meeting, MeetingMinutes, ActionItem, User, MeetingTemplate
from app.schemas import APIResponse, ActionItemCreate, ActionItemUpdate, ActionItemResponse, MinutesResponse, PYDANTIC_V2, to_response, build_meeting_data, serialize_action_items
from app.services.nlp_service import nlp_processor, deepseek_nlp_processor, local_qwen_processor
from app.services.minutes_service import minutes_generator
from app.routes.websocket import broadcast_inference_progress
from app.routes.auth import require_user
from config import UPLOAD_DIR

router = APIRouter(prefix="/api/minutes", tags=["纪要管理"])


@router.post("/generate/{meeting_id}")
async def generate_minutes(
    meeting_id: int,
    engine: str = Query("keyword", description="NLP引擎: keyword(关键词匹配) 或 deepseek(AI智能提取)"),
    max_tokens: int = Query(0, description="Qwen 输出 token 上限，0=使用默认值"),
    template_id: int = Query(0, description="模板ID，0表示使用默认结构"),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """为指定会议生成纪要"""
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id, Meeting.created_by == user.id).first()
    if not meeting:
        return APIResponse(success=False, message="会议记录不存在")
    if not meeting.raw_text:
        return APIResponse(success=False, message="会议没有可处理的文本内容")

    # 获取模板结构
    template_structure = None
    if template_id:
        template = db.query(MeetingTemplate).filter(MeetingTemplate.id == template_id).first()
        if template and template.content_structure:
            template_structure = template.content_structure

    # 根据 engine 参数选择处理器
    if engine == "deepseek":
        processor = deepseek_nlp_processor
        engine_msg = "DeepSeek AI 智能提取"
    elif engine == "qwen":
        processor = local_qwen_processor
        engine_msg = "Qwen3 本地模型"
    else:
        processor = nlp_processor
        engine_msg = "关键词匹配"

    loop = asyncio.get_event_loop()

    async def _progress_cb(progress, current, total, text=""):
        await broadcast_inference_progress(meeting_id, {
            "type": "progress",
            "progress": round(progress, 3),
            "current_tokens": current,
            "max_tokens": total,
            "text": text,
        })

    def _sync_progress_cb(progress, current, total, text=""):
        asyncio.run_coroutine_threadsafe(_progress_cb(progress, current, total, text), loop)

    progress_callback = _sync_progress_cb if engine == "qwen" else None

    await broadcast_inference_progress(meeting_id, {"type": "start", "engine": engine})

    import inspect
    sig = inspect.signature(processor.process)
    process_kwargs = {
        "text": meeting.raw_text,
        "title": meeting.title,
        "participants": meeting.participants or "",
    }
    if 'progress_callback' in sig.parameters:
        process_kwargs["max_tokens"] = max_tokens
        process_kwargs["progress_callback"] = progress_callback
    if 'template_structure' in sig.parameters and template_structure:
        process_kwargs["template_structure"] = template_structure

    nlp_result = await asyncio.to_thread(processor.process, **process_kwargs)

    await broadcast_inference_progress(meeting_id, {"type": "done"})

    # AI 提取的参会人员优先覆盖
    ai_participants = nlp_result.get("participants", "")
    if ai_participants and ai_participants.strip():
        meeting.participants = ai_participants.strip()
        db.flush()

    existing = db.query(MeetingMinutes).filter(MeetingMinutes.meeting_id == meeting_id).first()
    if existing:
        db.delete(existing)
        db.flush()

    minutes = MeetingMinutes(
        meeting_id=meeting_id,
        topic=nlp_result["topic"],
        overview=nlp_result["overview"],
        discussion_points=nlp_result["discussion_points"],
        key_decisions=nlp_result["key_decisions"],
        unresolved_issues=nlp_result["unresolved_issues"],
        summary=nlp_result["summary"],
    )
    db.add(minutes)
    db.flush()

    db.query(ActionItem).filter(ActionItem.meeting_id == meeting_id).delete()
    for item in nlp_result["action_items"]:
        action = ActionItem(
            meeting_id=meeting_id,
            content=item["content"],
            responsible_person=item.get("responsible_person", ""),
            deadline=item.get("deadline", ""),
            priority=item.get("priority", "medium"),
        )
        db.add(action)

    meeting.status = "completed"
    db.commit()

    meeting_data = {
        "title": meeting.title,
        "meeting_date": meeting.meeting_date.strftime("%Y年%m月%d日") if meeting.meeting_date else "",
        "participants": meeting.participants or "",
        **nlp_result,
    }
    markdown = minutes_generator.generate_markdown(meeting_data)
    html = minutes_generator.generate_html(meeting_data)

    # 缓存 markdown/html 到数据库，避免后续请求重新生成
    minutes.markdown = markdown
    minutes.html = html
    db.commit()

    return APIResponse(success=True, message=f"纪要生成成功（{engine_msg}）", data={
        "minutes_id": minutes.id,
        "engine": engine,
        "markdown": markdown,
        "html": html,
        "topic": nlp_result["topic"],
        "overview": nlp_result["overview"],
        "discussion_points": nlp_result["discussion_points"],
        "key_decisions": nlp_result["key_decisions"],
        "unresolved_issues": nlp_result["unresolved_issues"],
        "summary": nlp_result["summary"],
        "action_items": nlp_result["action_items"],
    })


@router.get("/{meeting_id}")
async def get_minutes(meeting_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """获取会议纪要（一次查询加载所有关联数据）"""
    meeting = (
        db.query(Meeting)
        .options(
            joinedload(Meeting.minutes),
            joinedload(Meeting.action_items),
        )
        .filter(Meeting.id == meeting_id, Meeting.created_by == user.id)
        .first()
    )
    if not meeting:
        return APIResponse(success=False, message="会议记录不存在")
    if not meeting.minutes:
        return APIResponse(success=False, message="纪要不存在，请先生成")

    minutes = meeting.minutes
    action_items = meeting.action_items

    # 优先使用缓存的 markdown/html，未缓存则重新生成（向后兼容）
    if minutes.markdown and minutes.html:
        markdown = minutes.markdown
        html = minutes.html
    else:
        meeting_data = build_meeting_data(meeting, minutes, action_items)
        markdown = minutes_generator.generate_markdown(meeting_data)
        html = minutes_generator.generate_html(meeting_data)

    return APIResponse(success=True, data={
        "markdown": markdown,
        "html": html,
        "action_items": [to_response(ActionItemResponse, a) for a in action_items],
    })


@router.post("/{meeting_id}/actions")
async def add_action_item(meeting_id: int, data: ActionItemCreate, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """添加行动项"""
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id, Meeting.created_by == user.id).first()
    if not meeting:
        return APIResponse(success=False, message="会议记录不存在")
    action = ActionItem(meeting_id=meeting_id, content=data.content,
                        responsible_person=data.responsible_person,
                        deadline=data.deadline, priority=data.priority)
    db.add(action)
    db.commit()
    db.refresh(action)
    return APIResponse(success=True, message="行动项添加成功", data={"id": action.id})


@router.put("/actions/{action_id}")
async def update_action_item(action_id: int, data: ActionItemUpdate, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """更新行动项"""
    action = db.query(ActionItem).filter(ActionItem.id == action_id).first()
    if not action:
        return APIResponse(success=False, message="行动项不存在")
    update_data = data.model_dump(exclude_unset=True) if PYDANTIC_V2 else data.dict(exclude_unset=True)
    for k, v in update_data.items():
        setattr(action, k, v)
    db.commit()
    return APIResponse(success=True, message="更新成功")


@router.delete("/actions/{action_id}")
async def delete_action_item(action_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """删除行动项"""
    action = db.query(ActionItem).filter(ActionItem.id == action_id).first()
    if not action:
        return APIResponse(success=False, message="行动项不存在")
    db.delete(action)
    db.commit()
    return APIResponse(success=True, message="删除成功")


