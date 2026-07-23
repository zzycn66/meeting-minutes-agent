# backend/app/services/streaming_service.py
# -*- coding: utf-8 -*-
"""流式语音识别服务"""
import io
import wave
import struct
import logging
import re
import numpy as np

from config import WHISPER_MODEL_SIZE as _WHISPER_MODEL_SIZE_RT
from app.utils.regex_patterns import (
    detect_prompt_echo as _detect_prompt_echo,
    detect_repetition as _detect_repetition,
    WHISPER_INITIAL_PROMPT as _WHISPER_INITIAL_PROMPT,
    WHISPER_TRANSCRIBE_KWARGS as _WHISPER_TRANSCRIBE_KWARGS,
)

logger = logging.getLogger(__name__)

_HALLUCINATION_PATTERNS = [
    re.compile(p) for p in [
        r'手机APP',
        r'安卓|Android',
        r'IOS|iOS',
        r'专业版|会员|订阅',
        r'下载|安装|更新',
        r'右上角|右下角|左上角|左下角',
        r'点击|长按|双击|滑动',
        r'应用商店|App\s*Store|Google\s*Play',
        r'免费下载|立即下载',
    ]
]

class StreamingTranscriber:
    """基于 faster-whisper 的流式语音识别"""

    def __init__(self, sample_rate=16000, chunk_duration=4.0, overlap_duration=0.8):
        self.sample_rate = sample_rate
        self.chunk_duration = chunk_duration
        self.overlap_duration = overlap_duration
        self.buffer = bytearray()
        self._context_text = ""
        self._input_sample_rate = None
        self._speaker_embeddings = []
        self._speaker_labels = []
        self._speaker_count = 0
        self._last_speaker = None
        self._last_speaker = None
        self._diarizer = None
        self._encoder = None
        self._init_diarizer()

    def _init_diarizer(self):
        """初始化说话人识别器"""
        try:
            from resemblyzer import VoiceEncoder
            self._encoder = VoiceEncoder()
            logger.info("Voice encoder loaded for streaming diarization")
        except Exception as e:
            logger.warning(f"Failed to load voice encoder: {e}")
            self._encoder = None

    def set_input_sample_rate(self, rate: int):
        """设置输入音频的采样率（浏览器 AudioContext 通常是 44100 或 48000）"""
        self._input_sample_rate = rate
        logger.info("Input sample rate set to %d", rate)

    def add_audio(self, audio_data: bytes):
        """添加音频数据到缓冲区"""
        self.buffer.extend(audio_data)

    def _resample_to_16k(self, int16_data: np.ndarray) -> np.ndarray:
        """将音频重采样到 16kHz（使用线性插值，比索引采样更平滑）"""
        if self._input_sample_rate is None or self._input_sample_rate == 16000:
            return int16_data
        src_len = len(int16_data)
        target_len = int(src_len * 16000 / self._input_sample_rate)
        src_x = np.linspace(0, 1, src_len)
        tgt_x = np.linspace(0, 1, target_len)
        return np.interp(tgt_x, src_x, int16_data.astype(np.float64)).astype(np.int16)

    def should_transcribe(self) -> bool:
        """检查缓冲区是否达到识别阈值"""
        input_rate = self._input_sample_rate or self.sample_rate
        expected_bytes = int(input_rate * 2 * (self.chunk_duration + self.overlap_duration))  # 16-bit mono
        return len(self.buffer) >= expected_bytes

    def _is_silence(self, audio_np: np.ndarray, threshold: float = 0.005) -> bool:
        """检测音频是否为静音（基于RMS能量）"""
        if len(audio_np) == 0:
            return True
        rms = np.sqrt(np.mean(audio_np ** 2))
        logger.info("Silence check: RMS=%.6f, threshold=%.4f", rms, threshold)
        return rms < threshold

    def _is_hallucination(self, text: str) -> bool:
        """检测是否为Whisper幻觉输出（重复文本、prompt echo或无意义内容）"""
        if not text or not text.strip():
            return True
        t = text.strip()
        if len(t) < 2:
            return True
        if _detect_repetition(t):
            logger.warning("Hallucination detected (repetition): %s", t[:50])
            return True
        if _detect_prompt_echo(t):
            logger.warning("Hallucination detected (prompt echo): %s", t[:50])
            return True
        if any(p.search(t) for p in _HALLUCINATION_PATTERNS):
            logger.warning("Hallucination detected (known pattern): %s", t[:50])
            return True
        return False

    def transcribe_chunk(self) -> str:
        """识别缓冲区中的音频，返回转写文本"""
        from app.services.speech_service import _get_faster_whisper_model

        if not self.buffer:
            logger.warning("transcribe_chunk: buffer empty!")
            return ""

        buf_len = len(self.buffer)
        logger.info("transcribe_chunk: input=%d bytes, input_rate=%s", buf_len, self._input_sample_rate)

        model = _get_faster_whisper_model()
        if model is None:
            logger.error("transcribe_chunk: model is None!")
            self.buffer.clear()
            return ""

        logger.info("transcribe_chunk: model loaded, converting audio...")
        int16_data = np.frombuffer(bytes(self.buffer), dtype=np.int16)
        resampled = self._resample_to_16k(int16_data)
        audio_np = resampled.astype(np.float32) / 32768.0

        logger.info("transcribe_chunk: %d bytes -> %d int16 samples -> %d resampled samples (%.2fs at 16kHz)",
                     buf_len, len(int16_data), len(audio_np), len(audio_np) / 16000)

        if self._is_silence(audio_np):
            logger.info("transcribe_chunk: silence detected, skipping transcription")
            self.buffer.clear()
            return ""

        try:
            # Build per-chunk kwargs optimized for medium model streaming
            chunk_kwargs = dict(_WHISPER_TRANSCRIBE_KWARGS)
            # medium model: use beam_size=4 for speed/accuracy balance
            chunk_kwargs["beam_size"] = 4
            chunk_kwargs["best_of"] = 5
            chunk_kwargs["temperature"] = 0.0
            chunk_kwargs["condition_on_previous_text"] = True
            chunk_kwargs["word_timestamps"] = False
            chunk_kwargs["compression_ratio_threshold"] = 2.4
            chunk_kwargs["log_prob_threshold"] = -1.0
            chunk_kwargs["no_speech_threshold"] = 0.6
            # Use accumulated context as initial_prompt to guide the model
            if self._context_text:
                context_tail = self._context_text[-300:]
                chunk_kwargs["initial_prompt"] = chunk_kwargs.get("initial_prompt", "") + " " + context_tail
            # Relaxed VAD for streaming (shorter min_silence to catch pauses)
            chunk_kwargs["vad_filter"] = True
            chunk_kwargs["vad_parameters"] = dict(
                min_silence_duration_ms=300,
                speech_pad_ms=400,
                threshold=0.25,
            )

            logger.info("transcribe_chunk: calling faster-whisper transcribe()...")
            segments, info = model.transcribe(
                audio_np,
                **chunk_kwargs,
            )

            seg_list = list(segments)
            text = " ".join(seg.text.strip() for seg in seg_list)
            logger.info("transcribe_chunk: DONE - %d segments, lang=%s, text='%s'",
                        len(seg_list), info.language if info else '?', text[:100] if text else "(empty)")

            if self._is_hallucination(text):
                logger.warning("transcribe_chunk: hallucination detected, discarding text")
                self.buffer.clear()
                return ""

            # Post-processing: traditional->simplified + punctuation restore (same as speech_service)
            if text:
                try:
                    from app.services.speech_service import _traditional_to_simplified, _restore_punctuation
                    text = _traditional_to_simplified(text)
                    text = _restore_punctuation(text)
                except Exception as post_err:
                    logger.warning("Post-processing failed: %s", post_err)

            if text:
                self._context_text = (self._context_text + " " + text).strip()[-500:]
                
                speaker = self._identify_speaker(audio_np)
                if speaker and speaker != self._last_speaker:
                    text = f"【{speaker}】{text}"
                    self._last_speaker = speaker

            # 保留 overlap 部分，防止截断导致识别错误
            input_rate = self._input_sample_rate or self.sample_rate
            overlap_bytes = int(input_rate * 2 * self.overlap_duration)
            if overlap_bytes > 0 and len(self.buffer) > overlap_bytes:
                self.buffer = self.buffer[-overlap_bytes:]
            else:
                self.buffer.clear()
            return text
        except Exception as e:
            logger.error("transcribe_chunk: FAILED - %s", e, exc_info=True)
            self.buffer.clear()
            return ""

    def reset(self):
        """重置缓冲区和上下文"""
        self.buffer.clear()
        self._context_text = ""
        self._speaker_embeddings = []
        self._speaker_labels = []
        self._speaker_count = 0

    def _identify_speaker(self, audio_np: np.ndarray) -> str:
        """识别音频片段的说话人"""
        if self._encoder is None or len(audio_np) < self.sample_rate * 0.5:
            return None
        
        try:
            embedding = self._encoder.embed_utterance(audio_np)
            
            if not self._speaker_embeddings:
                self._speaker_count = 1
                self._speaker_embeddings.append(embedding)
                self._speaker_labels.append(1)
                return "说话人1"
            
            similarities = []
            for existing_embedding in self._speaker_embeddings:
                similarity = np.dot(embedding, existing_embedding) / (
                    np.linalg.norm(embedding) * np.linalg.norm(existing_embedding)
                )
                similarities.append(similarity)
            
            max_similarity = max(similarities)
            threshold = 0.75
            
            if max_similarity >= threshold:
                speaker_idx = similarities.index(max_similarity)
                speaker_num = self._speaker_labels[speaker_idx]
                return f"说话人{speaker_num}"
            else:
                self._speaker_count += 1
                self._speaker_embeddings.append(embedding)
                self._speaker_labels.append(self._speaker_count)
                return f"说话人{self._speaker_count}"
        
        except Exception as e:
            logger.warning(f"Speaker identification failed: {e}")
            return None