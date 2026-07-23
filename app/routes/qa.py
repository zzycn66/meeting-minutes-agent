# -*- coding: utf-8 -*-
"""
智能问答 API 路由模块

本模块负责：
1. 提供同步问答接口（/qa）- 一次性返回完整回答
2. 提供流式问答接口（/qa/stream）- 使用 SSE 协议逐字输出

SSE (Server-Sent Events) 协议详解：

1. 什么是 SSE？
   - Server-Sent Events（服务端推送事件）
   - 一种服务端单向推送数据给客户端的技术
   - 基于 HTTP 协议，不需要特殊的服务器支持

2. SSE 数据格式：
   每条消息必须以 "data: " 开头，以两个换行符 "\\n\\n" 结尾
   ┌─────────────────────────────────────────┐
   │ data: {"text": "根据"}\n\n              │  ← 第一条消息
   │ data: {"text": "会议"}\n\n              │  ← 第二条消息
   │ data: {"text": "记录"}\n\n              │  ← 第三条消息
   │ data: {"done": true}\n\n                │  ← 完成信号
   └─────────────────────────────────────────┘

3. SSE vs WebSocket 对比：
   ┌──────────────┬─────────────────┬─────────────────┐
   │    特性       │     WebSocket   │       SSE       │
   ├──────────────┼─────────────────┼─────────────────┤
   │   通信方向   │    双向通信     │  服务端单向推送 │
   │   协议       │   ws:// 或 wss://│  http:// 或 https://│
   │   复杂度     │     较高        │      较低       │
   │   断线重连   │   需要手动实现  │   浏览器自动    │
   │   适用场景   │  聊天、游戏     │  AI生成、日志   │
   └──────────────┴─────────────────┴─────────────────┘

4. 为什么选择 SSE？
   - 问答是单向的（用户问，AI 答）
   - SSE 自动断线重连，更稳定
   - 实现更简单，基于 HTTP
   - 浏览器原生支持 EventSource API

5. 流式输出的优势：
   - 用户可以实时看到生成过程
   - 首字延迟低（不需要等待完整响应）
   - 可以实现打字机效果
   - 提升用户体验
"""
import json
import logging
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models import User, QAHistory
from app.schemas import APIResponse
from app.qa_service import QAService
from app.routes.auth import require_user

logger = logging.getLogger(__name__)

# 创建路由器，前缀为 /api/meetings
qa_router = APIRouter(prefix="/api/meetings", tags=["智能问答"])

# 创建问答服务实例（全局单例）
qa_service = QAService()


class QARequest(BaseModel):
    """问答请求模型 - 使用 Pydantic 进行数据验证"""
    question: str  # 用户问题（必填）


# ==================== 同步问答接口 ====================
@qa_router.post("/{meeting_id}/qa")
async def ask_question(
    meeting_id: int,
    request: QARequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """
    同步问答接口 - 一次性返回完整回答

    请求流程：
    1. 客户端发送 POST 请求，包含问题
    2. 服务端处理请求（可能需要几秒）
    3. 服务端返回完整回答
    4. 客户端一次性显示所有内容

    缺点：
    - 用户需要等待完整响应
    - 如果回答很长，首字延迟高
    - 用户体验较差
    """
    logger.info(f"/api/meetings/{meeting_id}/qa | question={request.question[:50]}...")

    # 调用问答服务
    result = qa_service.ask(meeting_id, request.question, db)

    if result["success"]:
        # 保存问答记录到数据库
        qa_record = QAHistory(
            meeting_id=meeting_id,
            question=request.question,
            answer=result["answer"]
        )
        db.add(qa_record)
        db.commit()

        return APIResponse(
            success=True,
            data={
                "answer": result["answer"],
                "sources": result.get("sources", [])  # 返回来源段落
            }
        )
    else:
        return APIResponse(success=False, message=result["message"])


# ==================== 流式问答接口 ====================
@qa_router.post("/{meeting_id}/qa/stream")
async def ask_question_stream(
    meeting_id: int,
    request: QARequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """
    流式问答接口 - 使用 SSE 协议逐字输出

    请求流程：
    1. 客户端发送 POST 请求，包含问题
    2. 服务端返回 HTTP 200，Content-Type 为 text/event-stream
    3. 服务端通过 HTTP 连接持续推送数据
    4. 客户端实时接收并显示（打字机效果）
    5. 推送完成后，服务端关闭连接

    优势：
    - 首字延迟低（第一个字很快就能显示）
    - 用户可以实时看到生成过程
    - 用户体验好（打字机效果）
    """
    logger.info(f"/api/meetings/{meeting_id}/qa/stream | question={request.question[:50]}...")

    def generate():
        """
        生成器函数 - 用于 SSE 流式输出

        生成器使用 yield 关键字，每次 yield 发送一条 SSE 消息。

        SSE 消息格式：
        ┌─────────────────────────────────────────┐
        │ data: {JSON数据}\n\n                    │
        └─────────────────────────────────────────┘

        示例：
        data: {"text": "根据"}\n\n
        data: {"text": "会议"}\n\n
        data: {"done": true}\n\n
        """
        full_answer = ""
        try:
            # ========== 步骤 1：验证会议是否存在 ==========
            from app.models import Meeting
            meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()

            if not meeting:
                # 发送错误消息（SSE 格式）
                yield f"data: {json.dumps({'error': '会议不存在'})}\n\n"
                return

            raw_text = meeting.raw_text or ""
            if not raw_text.strip():
                yield f"data: {json.dumps({'error': '该会议没有原始文本'})}\n\n"
                return

            # ========== 步骤 2：语义检索相关段落 ==========
            # 将会议文本分割为段落
            paragraphs = qa_service._split_paragraphs(raw_text)

            # 使用 Sentence-BERT 进行语义检索，找到与问题最相关的段落
            relevant = qa_service._semantic_search(paragraphs, request.question)

            # 将相关段落拼接为上下文
            context = "\n".join(relevant)

            # ========== 步骤 3：构造 Prompt ==========
            # Prompt 是给 AI 模型的指令
            prompt = (
                f"你是会议纪要助手。根据以下会议文本回答问题。尽量从文本中找到相关信息来回答。"
                f"即使信息不完全匹配，也请基于文本内容给出最相关的回答。\n\n"
                f"会议文本：\n{context}\n\n"
                f"问题：{request.question}\n\n"
                f"请直接回答："
            )

            # ========== 步骤 4：加载 Qwen3 模型 ==========
            from app.services.nlp_service import local_qwen_processor
            local_qwen_processor._ensure_model()  # 确保模型已加载

            # 获取 tokenizer（分词器）和 model（模型）
            tokenizer = local_qwen_processor.__class__._tokenizer
            model = local_qwen_processor.__class__._model

            # ========== 步骤 5：使用 Qwen3 流式生成 ==========
            # 构造消息格式
            messages = [{"role": "user", "content": prompt}]

            # 使用 Qwen3 的 chat template 格式化 prompt
            input_text = tokenizer.apply_chat_template(
                messages,
                tokenize=False,              # 不进行 tokenization
                add_generation_prompt=True,  # 添加生成提示
                enable_thinking=False        # 禁用思维链，加速推理
            )

            import torch
            from transformers import TextIteratorStreamer
            import threading

            # Tokenize 输入（将文本转换为模型能理解的 token 序列）
            inputs = tokenizer(
                input_text,
                return_tensors="pt",    # 返回 PyTorch 张量
                truncation=True,        # 截断过长的输入
                max_length=8192         # 最大输入长度
            )

            # 创建流式输出器
            # TextIteratorStreamer 会将模型生成的 token 逐个输出
            streamer = TextIteratorStreamer(
                tokenizer,
                skip_prompt=True,       # 跳过 prompt 部分（只输出生成的内容）
                skip_special_tokens=True  # 跳过特殊 token（如 <eos>）
            )

            # 推理参数
            gen_kwargs = dict(
                **inputs,                   # 输入 token
                max_new_tokens=512,         # 最大输出 token 数
                do_sample=False,            # 贪心解码（确定性输出）
                pad_token_id=tokenizer.eos_token_id,  # 填充 token
                streamer=streamer,          # 绑定流式输出器
            )

            # 在后台线程运行推理
            # 为什么要用后台线程？
            # 因为 model.generate() 是阻塞的，会阻塞主线程
            # 使用后台线程可以让主线程继续读取 streamer 的输出
            def _generate():
                with torch.inference_mode():  # 推理模式，节省内存
                    model.generate(**gen_kwargs)

            gen_thread = threading.Thread(target=_generate, daemon=True)
            gen_thread.start()

            # ========== 步骤 6：逐 token 推送给客户端 ==========
            # 从 streamer 中读取生成的文本，实时推送给客户端
            for new_text in streamer:
                if new_text.strip():
                    full_answer += new_text
                    # SSE 格式：data: {JSON}\n\n
                    yield f"data: {json.dumps({'text': new_text})}\n\n"

            # 保存问答记录到数据库
            if full_answer.strip():
                qa_record = QAHistory(
                    meeting_id=meeting_id,
                    question=request.question,
                    answer=full_answer
                )
                db.add(qa_record)
                db.commit()

            # 发送完成信号
            yield f"data: {json.dumps({'done': True})}\n\n"

        except Exception as e:
            logger.error(f"流式问答失败: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    # 返回 StreamingResponse
    # media_type="text/event-stream" 告诉浏览器这是 SSE 流
    return StreamingResponse(generate(), media_type="text/event-stream")
