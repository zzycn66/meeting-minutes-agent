# -*- coding: utf-8 -*-
"""会议业务逻辑服务层 — 从 routes/meetings.py 提取"""
import os
import re
import logging
from datetime import datetime

from app.models import Meeting
from app.services.nlp_service import nlp_processor
from app.services.speech_service import speech_recognizer
from config import UPLOAD_DIR, ALLOWED_AUDIO_EXTENSIONS, MAX_UPLOAD_SIZE

logger = logging.getLogger(__name__)

_KEY_WORDS_MAP = [
    (["产品", "需求", "功能", "版本", "迭代", "原型", "上线"], "产品规划讨论"),
    (["技术", "架构", "代码", "bug", "BUG", "部署", "接口", "API", "服务", "异常"], "技术方案评审"),
    (["测试", "用例", "质量", "缺陷", "回归"], "测试总结"),
    (["设计", "UI", "UX", "交互", "视觉"], "设计评审"),
    (["运营", "数据", "用户增长", "活动", "推广"], "运营复盘"),
    (["项目", "进度", "排期", "资源", "风险"], "项目进度同步"),
    (["客户", "甲方", "反馈", "投诉", "售后"], "客户反馈处理"),
    (["招聘", "面试", "绩效", "培训", "HR"], "人事沟通"),
]


class MeetingService:

    @staticmethod
    def generate_title(raw_text: str, meeting_name: str = None) -> str:
        """根据会议内容自动生成标题"""
        today = datetime.now().strftime("%Y/%m/%d")
        if meeting_name:
            return f"{meeting_name} 会议 {today}"

        text_sample = raw_text[:300] if raw_text else ""
        max_score = 0
        best_name = "工作讨论"
        for keywords, name in _KEY_WORDS_MAP:
            score = sum(1 for kw in keywords if kw in text_sample)
            if score > max_score:
                max_score = score
                best_name = name

        if max_score == 0 and raw_text:
            brief = re.sub(r'[\n\r\t]', ' ', raw_text[:50]).strip()
            brief = brief[:30] + ("..." if len(brief) > 30 else "")
            return f"会议 {today} - {brief}"

        return f"{best_name}会 {today}"

    @staticmethod
    def extract_participants(raw_text: str) -> str:
        """从会议内容中提取参会人员"""
        if not raw_text:
            return ""
        return nlp_processor.extract_participants(raw_text)

    @staticmethod
    async def save_audio(file) -> dict:
        """保存上传的音频文件"""
        ext = file.filename.split(".")[-1].lower() if "." in file.filename else ""
        if ext not in ALLOWED_AUDIO_EXTENSIONS:
            return {"success": False, "message": f"不支持的音频格式: {ext}，支持: {', '.join(ALLOWED_AUDIO_EXTENSIONS)}"}

        os.makedirs(UPLOAD_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"{timestamp}_{file.filename}"
        filepath = os.path.join(UPLOAD_DIR, filename)

        content = await file.read()
        if len(content) > MAX_UPLOAD_SIZE:
            return {"success": False, "message": f"文件大小超过限制 ({MAX_UPLOAD_SIZE // 1024 // 1024}MB)"}

        with open(filepath, "wb") as f:
            f.write(content)

        logger.info("File saved: %s, size: %d bytes", filepath, len(content))
        return {"success": True, "message": "文件上传成功", "data": {
            "filename": filename, "filepath": filepath, "size": len(content),
        }}

    @staticmethod
    def recognize(filepath: str = "", text: str = "", asr_engine: str = "") -> dict:
        """语音识别/文本处理"""
        if filepath:
            full_path = os.path.join(UPLOAD_DIR, os.path.basename(filepath))
            if not os.path.exists(full_path):
                full_path = filepath
            if not os.path.exists(full_path):
                return {"success": False, "message": f"音频文件不存在: {filepath}"}
            result = speech_recognizer.recognize_file(full_path, asr_engine=asr_engine)
        elif text:
            result = speech_recognizer.recognize_text(text)
        else:
            return {"success": False, "message": "请提供音频文件路径或文本内容"}

        return result

    @staticmethod
    def create_meeting(data, db) -> dict:
        """创建会议记录（业务编排）"""
        if not data.title and data.raw_text:
            data.title = MeetingService.generate_title(data.raw_text, data.meeting_name)
        elif not data.title:
            data.title = f"会议 {datetime.now().strftime('%Y/%m/%d %H:%M')}"

        meeting_date = datetime.strptime(data.meeting_date, "%Y-%m-%d") if data.meeting_date else datetime.now()

        participants = data.participants
        if not participants and data.raw_text:
            auto_participants = MeetingService.extract_participants(data.raw_text)
            if auto_participants:
                participants = auto_participants

        meeting = Meeting(
            title=data.title,
            meeting_date=meeting_date,
            duration=data.duration,
            participants=participants,
            input_type=data.input_type,
            raw_text=data.raw_text,
            status="completed" if data.raw_text else "processing",
            is_public=data.is_public if hasattr(data, 'is_public') else False,
            created_by=data.created_by if hasattr(data, 'created_by') else None,
        )
        db.add(meeting)
        db.commit()
        db.refresh(meeting)

        auto_info = {}
        if data.meeting_name and data.title:
            auto_info["auto_title"] = True
        if not data.participants and participants:
            auto_info["auto_participants"] = True

        return {
            "success": True,
            "message": "会议记录创建成功",
            "data": {
                "id": meeting.id,
                "title": meeting.title,
                "participants": meeting.participants,
                **auto_info,
            },
        }


meeting_service = MeetingService()
