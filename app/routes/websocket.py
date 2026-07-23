# -*- coding: utf-8 -*-
"""WebSocket 实时转写路由 + 推理进度推送"""
import os
import json
import asyncio
import re
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.streaming_service import StreamingTranscriber
from app.routes.auth import extract_token, get_current_user, active_sessions
from config import UPLOAD_DIR

logger = logging.getLogger(__name__)
router = APIRouter()

# ── 推理进度 WebSocket 连接池 ──
_inference_clients: dict[int, list[WebSocket]] = {}


async def _verify_ws_auth(websocket: WebSocket) -> bool:
    """Verify WebSocket connection has valid auth token"""
    token = websocket.query_params.get("token")
    logger.info("[WS AUTH] query_token=%s, cookies=%s", token, dict(websocket.cookies))
    if not token:
        token = websocket.cookies.get("session_token")
    logger.info("[WS AUTH] resolved_token=%s, valid=%s", token[:16] if token else None, token in active_sessions if token else False)
    if not token or token not in active_sessions:
        await websocket.close(code=4001, reason="请先登录")
        return False
    session = active_sessions[token]
    from datetime import datetime, timedelta
    if datetime.now() - session["created_at"] > timedelta(hours=24):
        del active_sessions[token]
        await websocket.close(code=4001, reason="会话已过期，请重新登录")
        return False
    return True


async def broadcast_inference_progress(meeting_id: int, data: dict):
    """向指定会议的所有推理进度监听者广播消息"""
    clients = _inference_clients.get(meeting_id, [])
    dead = []
    for ws in clients:
        try:
            await ws.send_json(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        clients.remove(ws)


@router.websocket("/ws/inference/{meeting_id}")
async def websocket_inference_progress(websocket: WebSocket, meeting_id: int):
    if not await _verify_ws_auth(websocket):
        return
    await websocket.accept()
    _inference_clients.setdefault(meeting_id, []).append(websocket)
    logger.info("Inference progress client connected: meeting_id=%d", meeting_id)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        logger.info("Inference progress client disconnected: meeting_id=%d", meeting_id)
    finally:
        clients = _inference_clients.get(meeting_id, [])
        if websocket in clients:
            clients.remove(websocket)

@router.websocket("/ws/transcribe")
async def websocket_transcribe(websocket: WebSocket):
    if not await _verify_ws_auth(websocket):
        return
    await websocket.accept()
    logger.info("WebSocket connected")
    transcriber = StreamingTranscriber()
    is_active = False
    is_transcribing = False

    try:
        while True:
            data = await websocket.receive()

            if data["type"] == "websocket.receive":
                if "text" in data:
                    msg = json.loads(data["text"])

                    if msg.get("type") == "start":
                        is_active = True
                        transcriber.reset()
                        if msg.get("sample_rate"):
                            transcriber.set_input_sample_rate(msg["sample_rate"])
                        logger.info("Start: mode=%s, sample_rate=%s", msg.get("mode"), msg.get("sample_rate"))

                        if msg.get("mode") == "file":
                            file_path = msg.get("file_path")
                            logger.info("[FILE WS] got file_path=%s, exists=%s", file_path, os.path.exists(os.path.join(UPLOAD_DIR, file_path) if file_path and not os.path.isabs(file_path) else (file_path or '')))
                            if file_path:
                                if not os.path.isabs(file_path):
                                    file_path = os.path.join(UPLOAD_DIR, file_path)
                                logger.info("[FILE WS] resolved file_path=%s, exists=%s", file_path, os.path.exists(file_path))
                                try:
                                    await _handle_file_transcription(websocket, transcriber, file_path)
                                except Exception as e:
                                    logger.error("[FILE WS] _handle_file_transcription raised: %s", e, exc_info=True)
                                    try:
                                        await websocket.send_json({"type": "error", "message": str(e)})
                                    except:
                                        pass
                                continue

                        await websocket.send_json({"type": "status", "message": "实时转写已启动"})

                    elif msg.get("type") == "stop":
                        is_active = False
                        logger.info("Stop: is_transcribing=%s, buffer=%d", is_transcribing, len(transcriber.buffer))
                        while is_transcribing:
                            await asyncio.sleep(0.1)
                        if transcriber.buffer:
                            logger.info("Transcribing final %d bytes", len(transcriber.buffer))
                            text = await asyncio.to_thread(transcriber.transcribe_chunk)
                            if text:
                                try:
                                    await websocket.send_json({"type": "transcript", "text": text, "is_final": True})
                                except Exception:
                                    pass
                        transcriber.reset()
                        try:
                            await websocket.send_json({"type": "status", "message": "实时转写已停止"})
                        except Exception:
                            pass

                elif "bytes" in data and is_active:
                    transcriber.add_audio(data["bytes"])

                    if transcriber.should_transcribe() and not is_transcribing:
                        buf = bytes(transcriber.buffer)
                        # 保留 overlap 部分，防止截断导致识别错误
                        input_rate = transcriber._input_sample_rate or transcriber.sample_rate
                        overlap_bytes = int(input_rate * 2 * transcriber.overlap_duration)
                        if overlap_bytes > 0 and len(transcriber.buffer) > overlap_bytes:
                            transcriber.buffer = transcriber.buffer[-overlap_bytes:]
                        else:
                            transcriber.buffer.clear()
                        logger.info("Queuing transcription: %d bytes", len(buf))

                        async def _do_transcribe(audio_buf):
                            nonlocal is_transcribing
                            is_transcribing = True
                            try:
                                logger.info(">>> Transcribe START: %d bytes", len(audio_buf))
                                t = StreamingTranscriber()
                                t.buffer = bytearray(audio_buf)
                                t._input_sample_rate = transcriber._input_sample_rate
                                t._context_text = transcriber._context_text
                                result = await asyncio.to_thread(t.transcribe_chunk)
                                logger.info("<<< Transcribe DONE: '%s'", result[:80] if result else "(empty)")
                                if result:
                                    transcriber._context_text = t._context_text
                                    try:
                                        await websocket.send_json({"type": "transcript", "text": result, "is_final": True})
                                        logger.info(">>> Transcript sent")
                                    except Exception:
                                        logger.info("Send failed (client disconnected)")
                                else:
                                    try:
                                        await websocket.send_json({"type": "newline"})
                                    except Exception:
                                        pass
                            except Exception as e:
                                logger.error("Transcribe error: %s", e)
                            finally:
                                is_transcribing = False

                        asyncio.create_task(_do_transcribe(buf))

    except WebSocketDisconnect:
        logger.info("Client disconnected")
    except Exception as e:
        logger.error("WebSocket error: %s", e)


async def _handle_file_transcription(websocket: WebSocket, transcriber: StreamingTranscriber, file_path: str):
    import wave
    import subprocess

    logger.info("[_handle_file_transcription] ENTER file_path=%s, exists=%s", file_path, os.path.exists(file_path))
    try:
        if not os.path.exists(file_path):
            await websocket.send_json({"type": "error", "message": f"文件不存在: {file_path}"})
            return

        await websocket.send_json({"type": "status", "message": "开始处理音频文件...", "progress": 0})
        wav_path = file_path + ".streaming.wav"
        logger.info("[_handle] calling ffmpeg: %s -> %s", file_path, wav_path)
        try:
            result = subprocess.run(
                ["ffmpeg", "-y", "-i", file_path, "-ar", "16000", "-ac", "1", "-f", "wav", wav_path],
                capture_output=True, timeout=60
            )
        except FileNotFoundError:
            await websocket.send_json({"type": "error", "message": "实时转写依赖 ffmpeg，但系统未检测到可执行文件，请安装或配置后重试"})
            return

        logger.info("[_handle] ffmpeg done: returncode=%d, wav_exists=%s, wav_size=%s", result.returncode, os.path.exists(wav_path), os.path.getsize(wav_path) if os.path.exists(wav_path) else None)
        if result.returncode != 0 or not os.path.exists(wav_path):
            stderr_text = result.stderr.decode("utf-8", errors="ignore").strip() if result.stderr else ""
            message = "音频格式转换失败"
            if "ffmpeg: not found" in stderr_text or "不是内部或外部命令" in stderr_text:
                message = "实时转写依赖 ffmpeg，但系统未检测到可执行文件，请安装或配置后重试"
            elif stderr_text:
                message = f"音频格式转换失败: {stderr_text[-200:]}"
            await websocket.send_json({"type": "error", "message": message})
            return

        logger.info("[_handle] opening wav for chunked transcription")
        with wave.open(wav_path, 'rb') as wf:
            total_frames = wf.getnframes()
            chunk_size = int(wf.getframerate() * 3)
            logger.info("[_handle] wav: total_frames=%d, chunk_size=%d, framerate=%d", total_frames, chunk_size, wf.getframerate())
            chunk_count = 0
            last_speaker = None
            while True:
                frames = wf.readframes(chunk_size)
                if not frames:
                    break
                transcriber.add_audio(frames)
                if transcriber.should_transcribe():
                    chunk_count += 1
                    logger.info("[_handle] chunk #%d, calling transcribe_chunk", chunk_count)
                    text = await asyncio.to_thread(transcriber.transcribe_chunk)
                    logger.info("[_handle] chunk #%d result: '%s'", chunk_count, text[:80] if text else "(empty)")
                    if text:
                        # Strip speaker label if same as last chunk
                        m = re.match(r'^【(说话人\d+)】', text)
                        if m:
                            spk = m.group(1)
                            if spk == last_speaker:
                                text = text[m.end():]
                            else:
                                last_speaker = spk
                        await websocket.send_json({"type": "transcript", "text": text, "is_final": True})
                    progress = wf.tell() / total_frames
                    await websocket.send_json({"type": "status", "message": "识别中...", "progress": round(progress, 2)})
                    logger.info("[_handle] chunk #%d progress sent: %.2f", chunk_count, progress)

        if transcriber.buffer:
            text = await asyncio.to_thread(transcriber.transcribe_chunk)
            if text:
                await websocket.send_json({"type": "transcript", "text": text, "is_final": True})

        await websocket.send_json({"type": "status", "message": "处理完成", "progress": 1.0})
        try:
            os.remove(wav_path)
        except:
            pass
        try:
            await websocket.close()
        except:
            pass
    except Exception as e:
        logger.error("File transcription failed: %s", e)
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except:
            pass
