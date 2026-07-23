# -*- coding: utf-8 -*-
"""数据库模型定义"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class Meeting(Base):
    """会议记录表"""
    __tablename__ = "meetings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False, comment="会议标题")
    meeting_date = Column(DateTime, default=datetime.now, comment="会议日期")
    duration = Column(String(50), comment="会议时长")
    participants = Column(String(500), comment="参会人员")
    input_type = Column(String(20), default="text", comment="输入类型: audio/text")
    raw_text = Column(Text, comment="原始文本/转写文本")
    audio_path = Column(String(500), comment="音频文件路径")
    status = Column(String(20), default="processing", comment="状态: processing/completed/failed")
    is_public = Column(Boolean, default=False, comment="是否公开")
    created_by = Column(Integer, ForeignKey("users.id"), comment="创建者ID")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    creator = relationship("User")

    minutes = relationship("MeetingMinutes", back_populates="meeting", uselist=False, cascade="all, delete-orphan")
    action_items = relationship("ActionItem", back_populates="meeting", cascade="all, delete-orphan")

class MeetingMinutes(Base):
    """会议纪要表"""
    __tablename__ = "meeting_minutes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"), unique=True, comment="关联会议ID")
    topic = Column(String(200), comment="会议议题")
    overview = Column(Text, comment="会议概述")
    discussion_points = Column(Text, comment="讨论要点")
    key_decisions = Column(Text, comment="关键决策")
    unresolved_issues = Column(Text, comment="遗留问题")
    summary = Column(Text, comment="会议总结")
    markdown = Column(Text, comment="生成的Markdown")
    html = Column(Text, comment="生成的HTML")
    created_at = Column(DateTime, default=datetime.now)

    meeting = relationship("Meeting", back_populates="minutes")

class ActionItem(Base):
    """行动项表"""
    __tablename__ = "action_items"
    __table_args__ = (
        Index("ix_action_items_meeting_id", "meeting_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"), comment="关联会议ID")
    content = Column(Text, nullable=False, comment="行动项内容")
    responsible_person = Column(String(100), comment="责任人")
    deadline = Column(String(50), comment="截止时间")
    priority = Column(String(20), default="medium", comment="优先级: high/medium/low")
    status = Column(String(20), default="pending", comment="状态: pending/in_progress/completed")
    created_at = Column(DateTime, default=datetime.now)

    meeting = relationship("Meeting", back_populates="action_items")

class User(Base):
    """用户表"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, comment="用户名")
    password_hash = Column(String(200), nullable=False, comment="密码哈希")
    display_name = Column(String(100), comment="显示名称")
    role = Column(String(20), default="user", comment="角色: admin/user")
    is_active = Column(Boolean, default=True, comment="是否激活")
    created_at = Column(DateTime, default=datetime.now)

class MeetingTemplate(Base):
    """会议模板表"""
    __tablename__ = "meeting_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="模板名称")
    description = Column(String(500), comment="模板描述")
    template_type = Column(String(50), comment="模板类型: weekly/project/review/training")
    content_structure = Column(Text, comment="会议结构模板（JSON格式）")
    default_topics = Column(Text, comment="默认议题")
    is_public = Column(Boolean, default=True, comment="是否公开")
    created_by = Column(Integer, ForeignKey("users.id"), comment="创建者ID")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    creator = relationship("User")

class QAHistory(Base):
    """问答历史表"""
    __tablename__ = "qa_history"
    __table_args__ = (
        Index("ix_qa_history_meeting_id", "meeting_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"), comment="关联会议ID")
    question = Column(Text, nullable=False, comment="用户问题")
    answer = Column(Text, comment="AI回答")
    created_at = Column(DateTime, default=datetime.now)

    meeting = relationship("Meeting")
