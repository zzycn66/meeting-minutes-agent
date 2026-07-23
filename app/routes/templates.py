# -*- coding: utf-8 -*-
"""会议模板API路由"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel
from datetime import datetime

from app.database import get_db
from app.models import MeetingTemplate, User
from app.schemas import APIResponse, PYDANTIC_V2
from app.routes.auth import require_user

router = APIRouter(prefix="/api/templates", tags=["会议模板"])

class TemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    template_type: Optional[str] = None
    content_structure: Optional[str] = None
    default_topics: Optional[str] = None
    is_public: bool = True

class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    template_type: Optional[str] = None
    content_structure: Optional[str] = None
    default_topics: Optional[str] = None
    is_public: Optional[bool] = None

if PYDANTIC_V2:
    from pydantic import ConfigDict

    class TemplateResponse(BaseModel):
        model_config = ConfigDict(from_attributes=True)

        id: int
        name: str
        description: Optional[str] = None
        template_type: Optional[str] = None
        content_structure: Optional[str] = None
        default_topics: Optional[str] = None
        is_public: bool
        created_by: Optional[int] = None
        created_at: Optional[datetime] = None
        updated_at: Optional[datetime] = None
else:
    class TemplateResponse(BaseModel):
        id: int
        name: str
        description: Optional[str] = None
        template_type: Optional[str] = None
        content_structure: Optional[str] = None
        default_topics: Optional[str] = None
        is_public: bool
        created_by: Optional[int] = None
        created_at: Optional[datetime] = None
        updated_at: Optional[datetime] = None

        class Config:
            orm_mode = True

def _to_response(obj):
    if PYDANTIC_V2:
        return TemplateResponse.model_validate(obj).model_dump()
    else:
        return TemplateResponse.from_orm(obj).dict()

@router.get("")
async def list_templates(
    template_type: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """获取模板列表"""
    query = db.query(MeetingTemplate).filter(MeetingTemplate.is_public == True)
    
    if template_type:
        query = query.filter(MeetingTemplate.template_type == template_type)
    
    if search:
        query = query.filter(MeetingTemplate.name.contains(search))
    
    templates = query.order_by(MeetingTemplate.created_at.desc()).all()
    return APIResponse(success=True, data={
        "items": [_to_response(t) for t in templates],
        "total": len(templates)
    })

@router.get("/types")
async def get_template_types():
    """获取模板类型列表"""
    types = [
        {"value": "weekly", "label": "周会/例会"},
        {"value": "project", "label": "项目会议"},
        {"value": "review", "label": "评审会议"},
        {"value": "training", "label": "培训会议"},
        {"value": "brainstorm", "label": "头脑风暴"},
        {"value": "other", "label": "其他"}
    ]
    return {"success": True, "data": types}

@router.get("/{template_id}")
async def get_template(template_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """获取模板详情"""
    template = db.query(MeetingTemplate).filter(MeetingTemplate.id == template_id).first()
    if not template:
        return APIResponse(success=False, message="模板不存在")
    return APIResponse(success=True, data=_to_response(template))

@router.post("")
async def create_template(data: TemplateCreate, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """创建模板"""
    template = MeetingTemplate(
        name=data.name,
        description=data.description,
        template_type=data.template_type,
        content_structure=data.content_structure,
        default_topics=data.default_topics,
        is_public=data.is_public,
        created_by=user.id
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return APIResponse(success=True, message="模板创建成功", data=_to_response(template))

@router.put("/{template_id}")
async def update_template(template_id: int, data: TemplateUpdate, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """更新模板"""
    template = db.query(MeetingTemplate).filter(MeetingTemplate.id == template_id).first()
    if not template:
        return APIResponse(success=False, message="模板不存在")

    update_data = data.model_dump(exclude_unset=True) if PYDANTIC_V2 else data.dict(exclude_unset=True)
    for k, v in update_data.items():
        setattr(template, k, v)

    template.updated_at = datetime.now()
    db.commit()
    return APIResponse(success=True, message="模板更新成功")

@router.delete("/{template_id}")
async def delete_template(template_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """删除模板"""
    template = db.query(MeetingTemplate).filter(MeetingTemplate.id == template_id).first()
    if not template:
        return APIResponse(success=False, message="模板不存在")
    db.delete(template)
    db.commit()
    return APIResponse(success=True, message="模板删除成功")

@router.post("/init-defaults")
async def init_default_templates(db: Session = Depends(get_db), user: User = Depends(require_user)):
    """初始化默认模板"""
    default_templates = [
        {
            "name": "周会/例会",
            "description": "常规周会，汇报本周工作和下周计划",
            "template_type": "weekly",
            "content_structure": "1. 本周工作总结\n2. 遇到的问题和解决方案\n3. 下周工作计划\n4. 需要协调的事项",
            "default_topics": "工作汇报、问题讨论、计划安排"
        },
        {
            "name": "项目进度会议",
            "description": "项目进度同步和风险评估",
            "template_type": "project",
            "content_structure": "1. 项目整体进度\n2. 各模块进展\n3. 风险和障碍\n4. 资源需求\n5. 里程碑更新",
            "default_topics": "进度汇报、风险评估、资源协调"
        },
        {
            "name": "需求评审会议",
            "description": "产品需求评审和确认",
            "template_type": "review",
            "content_structure": "1. 需求背景\n2. 功能需求说明\n3. 技术可行性分析\n4. 开发排期\n5. 待确认事项",
            "default_topics": "需求确认、技术方案、开发计划"
        },
        {
            "name": "培训/分享会议",
            "description": "技术分享或培训会议",
            "template_type": "training",
            "content_structure": "1. 培训主题\n2. 核心内容要点\n3. 实践案例\n4. 讨论问题\n5. 后续学习资源",
            "default_topics": "知识分享、技能培训、经验交流"
        },
        {
            "name": "头脑风暴会议",
            "description": "创意讨论和方案探索",
            "template_type": "brainstorm",
            "content_structure": "1. 议题说明\n2. 创意收集\n3. 方案评估\n4. 行动计划\n5. 后续跟进",
            "default_topics": "创意讨论、方案评估、行动计划"
        }
    ]
    
    created_count = 0
    for template_data in default_templates:
        existing = db.query(MeetingTemplate).filter(
            MeetingTemplate.name == template_data["name"]
        ).first()
        if not existing:
            template = MeetingTemplate(**template_data, is_public=True)
            db.add(template)
            created_count += 1
    
    db.commit()
    return APIResponse(success=True, message=f"初始化完成，创建了{created_count}个默认模板")
