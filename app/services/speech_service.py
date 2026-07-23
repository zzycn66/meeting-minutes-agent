# -*- coding: utf-8 -*-
"""语音识别服务模块 - faster-whisper加速 + MiMo ASR + 繁简转换"""
import os
import re
import logging

from config import WHISPER_MODEL_SIZE, MIMO_API_KEY, MIMO_ASR_BASE_URL
from app.utils.regex_patterns import (
    RE_SENT_SPLIT as _RE_SENTSplit, RE_DIGIT_LINE as _RE_DIGIT_LINE,
    RE_PERSON_EXTRACT as _RE_PERSON_EXTRACT,
    RE_PARTICIPANT_LABEL as _RE_PARTICIPANT_LABEL,
    RE_PARTICIPANT_SPLIT as _RE_PARTICIPANT_SPLIT,
    RE_PERSON_PATTERNS as _RE_PERSON_PATTERNS,
    RE_DEADLINE_PATTERNS as _RE_DEADLINE_PATTERNS,
    detect_prompt_echo as _detect_prompt_echo,
    detect_repetition as _detect_repetition,
    WHISPER_INITIAL_PROMPT as _WHISPER_INITIAL_PROMPT,
    WHISPER_TRANSCRIBE_KWARGS as _WHISPER_TRANSCRIBE_KWARGS,
)

logger = logging.getLogger(__name__)

_faster_whisper_model = None
_whisper_model = None
_jieba_posseg = None

try:
    import jieba
except ImportError:
    jieba = None


def _get_faster_whisper_model():
    """使用 faster-whisper (CTranslate2) 加速推理，速度提升 2-4x"""
    global _faster_whisper_model
    if _faster_whisper_model is not None:
        return _faster_whisper_model

    try:
        from faster_whisper import WhisperModel
        compute_type = "int8" if os.environ.get("LOCAL_MODEL_DEVICE", "cpu") == "cpu" else "float16"
        logger.info("Loading faster-whisper model: %s, compute_type=%s", WHISPER_MODEL_SIZE, compute_type)
        _faster_whisper_model = WhisperModel(
            WHISPER_MODEL_SIZE,
            device=os.environ.get("LOCAL_MODEL_DEVICE", "cpu"),
            compute_type=compute_type,
        )
        logger.info("faster-whisper model loaded")
        return _faster_whisper_model
    except ImportError:
        logger.warning("faster-whisper not installed, falling back to openai-whisper")
        return None


def _get_whisper_model():
    """兜底：openai-whisper 原版模型"""
    global _whisper_model
    if _whisper_model is None:
        import whisper
        _whisper_model = whisper.load_model(WHISPER_MODEL_SIZE)
    return _whisper_model


# 常用繁简对照表（兜底用）
_T2S_DICT = {
    "會": "会", "來": "来", "對": "对", "開": "开", "關": "关",
    "動": "动", "學": "学", "實": "实", "現": "现", "發": "发",
    "說": "说", "話": "话", "為": "为", "經": "经", "過": "过",
    "進": "进", "總": "总", "結": "结", "還": "还", "沒": "没",
    "這": "这", "從": "从", "當": "当", "幾": "几", "機": "机",
    "員": "员", "頭": "头", "業": "业", "無": "无", "與": "与",
    "於": "于", "並": "并", "處": "处", "萬": "万", "麼": "么",
    "點": "点", "應": "应", "該": "该", "將": "将", "讓": "让",
    "報": "报", "戰": "战", "際": "际", "體": "体", "時": "时",
    "後": "后", "個": "个", "們": "们", "問": "问", "題": "题",
    "啓": "启", "週": "周", "張": "张", "趙": "赵", "調": "调",
    "檔": "档", "遺": "遗", "隱": "隐", "數": "数", "據": "据",
    "詢": "询", "務": "务", "統": "统", "測": "测", "試": "试",
    "決": "决", "討": "讨", "論": "论", "劃": "划", "計": "计",
    "設": "设", "計": "计", "確": "确", "認": "认", "選": "选",
    "擇": "择", "驗": "验", "證": "证", "資": "资", "訊": "讯",
    "網": "网", "絡": "络", "電": "电", "腦": "脑", "視": "视",
    "頻": "频", "導": "导", "師": "师", "衛": "卫", "護": "护",
    "醫": "医", "藥": "药", "標": "标", "準": "准", "製": "制",
    "術": "术", "聲": "声", "職": "职", "權": "权", "義": "义",
    "內": "内", "區": "区", "國": "国", "際": "际", "際": "际",
    "賣": "卖", "買": "买", "車": "车", "馬": "马", "風": "风",
    "雲": "云", "門": "门", "飛": "飞", "魚": "鱼", "鳥": "鸟",
}



def _traditional_to_simplified(text: str) -> str:
    """繁体转简体"""
    try:
        from zhconv import convert
        return convert(text, "zh-cn")
    except ImportError:
        pass
    try:
        from opencc import OpenCC
        return OpenCC("t2s").convert(text)
    except ImportError:
        pass
    result = text
    for k, v in _T2S_DICT.items():
        result = result.replace(k, v)
    return result



# ── 标点恢复 ──

# 常见中文连接词，前面加逗号
_CONNECTOR_WORDS = [
    # 转折 / 因果 / 递进
    "但是", "不过", "然而", "所以", "因此", "而且", "并且",
    "然后", "接着", "另外", "此外", "同时", "还有",
    "首先", "其次", "最后", "总之", "其实", "当然",
    "如果", "虽然", "因为", "由于", "既然", "尽管",
    "无论", "不管", "除非", "只要", "只有",
    # 举例 / 解释
    "比如", "例如", "像", "包括", "就是说", "换句话说",
    # 话题 / 视角
    "关于", "对于", "针对",
    "一方面", "另一方面",
    # 枚举 / 分项（长词优先，避免短词截断"第一版"）
    "第一点", "第二点", "第三点",
    "第一", "第二", "第三", "第四", "第五",
    "一是", "二是", "三是", "四是",
    "另一个",
    # 时间 / 顺序
    "接下来", "之后", "以后",
    # 口语停顿标记
    "就是说", "怎么说呢", "然后呢", "就是", "那么",
]

# 需要边界检查的枚举词（避免截断"第一版""另一个"等复合词）
_ENUMERATORS = {"第一", "第二", "第三", "第四", "第五", "另一个"}
# 枚举词后跟这些字时视为复合词内部（如"第一版""第一集"），不加逗号
_ENUM_COMPOUND_NEXT = {"版", "集", "个", "次", "名", "位", "种", "项", "件", "条", "张", "批", "期", "步", "部分", "阶段", "轮"}

# 句末词，后面加句号
_SENTENCE_END_WORDS = {"了", "的", "吧", "啊", "哦", "呀", "嘛", "呢", "吗", "过", "着", "地", "得"}

# 疑问词，后面加问号（在句末时）
_QUESTION_WORDS = {"吗", "呢", "吧"}

# ── 预编译正则（仅本模块独有的）──
_RE_PUNCTS = re.compile(r"[。，！？、；：""''（）]")
_RE_PERIODNormalize = re.compile(r"[。.!?？！]+")
_RE_COMMANormalize = re.compile(r"[，,、]+")
_RE_PARASplit = re.compile(r"[\n\r]+")

# ── 缓存排序后的连接词列表 ──
_SORTED_CONNECTORS = sorted(_CONNECTOR_WORDS, key=len, reverse=True)

# ── 合并正则：一次扫描匹配所有连接词（性能关键）──
_CONNECTOR_PATTERNS_RE = re.compile("|".join(re.escape(cw) for cw in _SORTED_CONNECTORS))


def _get_jieba_posseg():
    """懒加载 jieba.posseg，避免首次导入慢"""
    global _jieba_posseg
    if _jieba_posseg is None and jieba is not None:
        try:
            import jieba.posseg as pseg
            _jieba_posseg = pseg
        except ImportError:
            pass
    return _jieba_posseg


def _restore_punctuation(text: str) -> str:
    """为无标点的中文文本恢复标点符号"""
    if not text or not text.strip():
        return text

    existing_puncts = _RE_PUNCTS.findall(text)
    if len(existing_puncts) >= 5 and len(text) < 50:
        return text

    text = _RE_PERIODNormalize.sub("。", text)
    text = _RE_COMMANormalize.sub("，", text)

    paragraphs = _RE_PARASplit.split(text.strip())
    result_parts = []

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        para = _split_on_mid_particles(para)
        sub_paras = para.split("\n")
        sub_results = []
        for sp in sub_paras:
            sp = sp.strip()
            if not sp:
                continue

            punctuated = _insert_commas_text(sp)
            if jieba:
                punctuated = _insert_commas_jieba(punctuated)
            punctuated = _insert_periods_by_length(punctuated)
            punctuated = _insert_periods(punctuated)
            sub_results.append(punctuated)

        result_parts.append("".join(sub_results))

    return "\n".join(result_parts)


# ── 预编译语气词切分：合并为单次扫描 ──
_MID_BREAK_RE = re.compile(r"(呢|吧|啊|哦|呀|嘛)(?=[\u4e00-\u9fff\d])")


def _split_on_mid_particles(text: str) -> str:
    """将句中出现的语气词后插入换行，切分为独立子句（单次扫描）"""
    return _MID_BREAK_RE.sub(r"\1\n", text)


def _insert_commas_text(text: str) -> str:
    """合并正则单次扫描匹配所有连接词并插入逗号"""
    inserts = []
    for m in _CONNECTOR_PATTERNS_RE.finditer(text):
        cw = m.group()
        pos = m.start()
        if pos > 0 and text[pos - 1] == "，":
            continue
        if cw in _ENUMERATORS:
            end = m.end()
            skip = False
            for suffix in _ENUM_COMPOUND_NEXT:
                if text[end:end + len(suffix)] == suffix:
                    skip = True
                    break
            if skip:
                continue
        inserts.append(pos)
    if not inserts:
        return text
    inserts.sort()
    result = list(text)
    for pos in reversed(inserts):
        result.insert(pos, "，")
    return "".join(result)


def _insert_commas_jieba(text: str) -> str:
    """jieba 分词后合并正则匹配，补充文本级遗漏"""
    clean = text.replace("，", "")
    words = list(jieba.cut(clean))
    joined = "".join(words)
    inserts = []
    for m in _CONNECTOR_PATTERNS_RE.finditer(joined):
        cw = m.group()
        pos = m.start()
        if pos > 0 and joined[pos - 1] == "，":
            continue
        if cw in _ENUMERATORS:
            end = m.end()
            skip = False
            for suffix in _ENUM_COMPOUND_NEXT:
                if joined[end:end + len(suffix)] == suffix:
                    skip = True
                    break
            if skip:
                continue
        inserts.append(pos)
    if not inserts:
        return text
    inserts.sort()
    result = list(joined)
    for pos in reversed(inserts):
        result.insert(pos, "，")
    return "".join(result)


def _insert_periods_by_length(text: str) -> str:
    """对过长的无逗号片段按长度插入逗号"""
    MIN_CLAUSE_LEN = 30
    result = []
    for chunk in text.split("。"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if len(chunk) > MIN_CLAUSE_LEN:
            segments = chunk.split("，")
            rebuilt = []
            buf = ""
            for seg in segments:
                if buf and len(buf) + len(seg) > MIN_CLAUSE_LEN:
                    rebuilt.append(buf + "，")
                    buf = seg
                else:
                    buf = buf + "，" + seg if buf else seg
            if buf:
                rebuilt.append(buf)
            chunk = "".join(rebuilt)
        result.append(chunk)
    return "。".join(result)


def _insert_periods(text: str) -> str:
    """在适当位置插入句号和问号"""
    clauses = text.split("，")
    result = []
    for i, clause in enumerate(clauses):
        clause = clause.strip()
        if not clause:
            continue
        is_last = (i == len(clauses) - 1)
        if any(clause.endswith(qw) for qw in _QUESTION_WORDS):
            result.append(clause + "？")
        elif is_last:
            result.append(clause + "。")
        elif len(clause) >= 6 and any(clause.endswith(ew) for ew in _SENTENCE_END_WORDS):
            result.append(clause + "。")
        else:
            result.append(clause + "，")
    return "".join(result)



def _whisper_postprocess(text: str, engine_name: str) -> dict:
    """Whisper公共后处理：繁简转换、标点恢复、prompt echo检测、重复幻觉检测"""
    text = _traditional_to_simplified(text)
    text = _restore_punctuation(text)
    if _detect_prompt_echo(text):
        logger.warning("Detected prompt echo in %s, treating as decode failure", engine_name)
        return {"success": False, "text": "", "message": "音频无有效内容，请重新录音或检查麦克风", "engine_used": engine_name}
    if _detect_repetition(text):
        logger.warning("Detected repetition hallucination in %s, discarding: %s", engine_name, text[:50])
        return {"success": False, "text": "", "message": "检测到重复内容，请重新录音", "engine_used": engine_name}
    return {"success": True, "text": text}


class SpeechRecognizer:

    def __init__(self):
        pass

    def is_whisper_available(self) -> bool:
        try:
            from faster_whisper import WhisperModel
            return True
        except ImportError:
            pass
        try:
            import whisper
            return True
        except ImportError:
            return False

    def is_mimo_configured(self) -> bool:
        return bool(MIMO_API_KEY and MIMO_API_KEY.strip())

    def recognize_file(self, audio_path: str, asr_engine: str = "") -> dict:
        if not os.path.exists(audio_path):
            return {"success": False, "text": "", "message": f"音频文件不存在: {audio_path}", "engine_used": ""}

        ext = os.path.splitext(audio_path)[1].lower()
        size_kb = os.path.getsize(audio_path) / 1024
        logger.info("file=%s ext=%s size=%.0fKB", os.path.basename(audio_path), ext, size_kb)

        # 手动选择
        if asr_engine == "whisper":
            if _get_faster_whisper_model() is not None:
                logger.info(">>> 手动选择: Whisper (faster)")
                return self._recognize_faster_whisper(audio_path)
            elif self.is_whisper_available():
                logger.info(">>> 手动选择: Whisper (openai)")
                return self._recognize_whisper(audio_path)
            logger.warning("Whisper 不可用，回退到自动选择")
        elif asr_engine == "mimo":
            if self.is_mimo_configured():
                logger.info(">>> 手动选择: MiMo ASR")
                return self._recognize_mimo(audio_path)
            logger.warning("MiMo 未配置，回退到自动选择")

        # 自动选择：Whisper(免费) > MiMo(付费)
        logger.info(">>> 自动选择 (用户选择: %s)", asr_engine or 'auto')
        faster_model = _get_faster_whisper_model()
        avail = []
        if faster_model is not None:
            avail.append("faster-whisper")
        elif self.is_whisper_available():
            avail.append("openai-whisper")
        if self.is_mimo_configured():
            avail.append("mimo")
        logger.info("可用引擎: %s", ', '.join(avail) if avail else '无')

        if faster_model is not None:
            return self._recognize_faster_whisper(audio_path)
        elif self.is_whisper_available():
            return self._recognize_whisper(audio_path)
        elif self.is_mimo_configured():
            return self._recognize_mimo(audio_path)
        else:
            return self._recognize_local_prompt(audio_path)

    def recognize_text(self, text: str) -> dict:
        if not text or not text.strip():
            return {"success": False, "text": "", "message": "输入文本为空"}
        cleaned = _traditional_to_simplified(text.strip())
        cleaned = _restore_punctuation(cleaned)
        return {"success": True, "text": cleaned, "message": "文本输入处理完成"}

    def _recognize_faster_whisper(self, audio_path: str) -> dict:
        """使用 faster-whisper (CTranslate2) 加速识别，比 openai-whisper 快 2-4 倍"""
        try:
            import time
            logger.info("faster-whisper transcribe start: %s", audio_path)
            t0 = time.time()

            converted_path = self._ensure_wav(audio_path)
            model = _get_faster_whisper_model()

            segments, info = model.transcribe(
                converted_path,
                **_WHISPER_TRANSCRIBE_KWARGS,
            )

            seg_list = list(segments)
            elapsed = time.time() - t0
            logger.info("faster-whisper done in %.1fs, segments: %d", elapsed, len(seg_list))

            if converted_path != audio_path and os.path.exists(converted_path):
                try:
                    os.remove(converted_path)
                except OSError:
                    pass

            text = "".join(seg.text.strip() for seg in seg_list)
            result = _whisper_postprocess(text, "faster-whisper")
            if not result["success"]:
                return result

            logger.info("faster-whisper speed: %.0f chars/sec", len(result["text"])/elapsed)
            
            # 尝试说话人识别
            try:
                from app.speaker_diarization import SpeakerDiarization
                diarizer = SpeakerDiarization()
                if diarizer.has_resemblyzer and diarizer.has_sklearn:
                    diarization_result = diarizer.diarize(audio_path)
                    if diarization_result:
                        text_with_speakers = self._add_speaker_labels(result["text"], diarization_result)
                        result["text"] = text_with_speakers
                        result["diarization"] = diarization_result
            except Exception as e:
                logger.warning(f"说话人识别失败，使用原始文本: {e}")
            
            return {"success": True, "text": result["text"], "message": f"faster-whisper 识别完成 ({elapsed:.1f}s)", "engine_used": "faster-whisper"}
        except Exception as e:
            logger.error("faster-whisper failed: %s, falling back to openai-whisper", e)
            return self._recognize_whisper(audio_path)

    def _recognize_whisper(self, audio_path: str) -> dict:
        try:
            logger.info("Whisper transcribe start: %s", audio_path)

            converted_path = self._ensure_wav(audio_path)
            model = _get_whisper_model()
            logger.info("Whisper model loaded, transcribing...")

            result = model.transcribe(
                converted_path,
                language="zh",
                task="transcribe",
                verbose=False,
                word_timestamps=False,
                temperature=0.0,
                best_of=5,
                beam_size=5,
                condition_on_previous_text=False,
                initial_prompt=_WHISPER_INITIAL_PROMPT,
            )
            logger.info("Whisper done, segments: %d", len(result.get('segments', [])))

            if converted_path != audio_path and os.path.exists(converted_path):
                try:
                    os.remove(converted_path)
                except OSError:
                    pass

            segments = result.get("segments", [])
            text = "".join(seg["text"].strip() + "。" for seg in segments) if segments else result.get("text", "").strip()

            post_result = _whisper_postprocess(text, "openai-whisper")
            if not post_result["success"]:
                return post_result

            # 尝试说话人识别
            try:
                from app.speaker_diarization import SpeakerDiarization
                diarizer = SpeakerDiarization()
                if diarizer.has_resemblyzer and diarizer.has_sklearn:
                    diarization_result = diarizer.diarize(audio_path)
                    if diarization_result:
                        text_with_speakers = self._add_speaker_labels(post_result["text"], diarization_result)
                        post_result["text"] = text_with_speakers
                        post_result["diarization"] = diarization_result
            except Exception as e:
                logger.warning(f"说话人识别失败，使用原始文本: {e}")

            return {"success": True, "text": post_result["text"], "message": "Whisper 本地识别完成", "engine_used": "openai-whisper"}
        except Exception as e:
            return {"success": False, "text": "", "message": f"Whisper 识别失败: {str(e)}", "engine_used": "openai-whisper"}

    def _ensure_wav(self, audio_path: str) -> str:
        """如果不是 wav 格式，用 ffmpeg 转换"""
        ext = os.path.splitext(audio_path)[1].lower()
        if ext == ".wav":
            return audio_path

        wav_path = audio_path + ".converted.wav"
        try:
            import subprocess
            result = subprocess.run(
                ["ffmpeg", "-y", "-i", audio_path, "-ar", "16000", "-ac", "1", "-f", "wav", wav_path],
                capture_output=True, timeout=60,
            )
            if result.returncode == 0 and os.path.exists(wav_path) and os.path.getsize(wav_path) > 100:
                logger.info("ffmpeg converted %s -> wav, size: %d", ext, os.path.getsize(wav_path))
                return wav_path
            else:
                err = result.stderr.decode("utf-8", errors="replace")[:200] if result.stderr else "unknown"
                logger.error("ffmpeg failed: %s", err)
                return audio_path
        except FileNotFoundError:
            logger.warning("ffmpeg not found, using original file")
            return audio_path
        except Exception as e:
            logger.error("ffmpeg error: %s", e)
            return audio_path

    def _recognize_local_prompt(self, audio_path: str) -> dict:
        ext = os.path.splitext(audio_path)[1].lower()
        return {
            "success": True,
            "text": (
                "[语音识别服务未配置]\n"
                f"音频文件: {os.path.basename(audio_path)} ({ext})\n\n"
                "可用方案：\n"
                "1. 安装本地模型: pip install openai-whisper\n"
                "2. 配置 MiMo ASR: 设置 MIMO_API_KEY 环境变量\n"
                "3. 切换到手动输入模式粘贴会议内容"
            ),
            "message": "NO_SERVICE_CONFIGURED",
            "engine_used": "none",
        }

    def _recognize_mimo(self, audio_path: str) -> dict:
        """使用 MiMo-V2.5-ASR 云端识别"""
        try:
            import base64
            import requests

            ext = os.path.splitext(audio_path)[1].lower()

            # 需要转换为 wav 的格式
            need_convert = ext not in (".wav", ".mp3")
            if need_convert:
                converted_path = self._ensure_wav(audio_path)
                audio_path = converted_path

            with open(audio_path, "rb") as f:
                audio_bytes = f.read()

            ext = os.path.splitext(audio_path)[1].lower()
            mime_map = {".wav": "audio/wav", ".mp3": "audio/mpeg"}
            mime_type = mime_map.get(ext, "audio/wav")

            file_size_mb = len(audio_bytes) / (1024 * 1024)
            if file_size_mb > 10:
                return {"success": False, "text": "", "message": f"音频文件过大 ({file_size_mb:.1f}MB)，MiMo ASR 限制 10MB", "engine_used": "mimo"}

            audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")

            logger.info("MiMo ASR start: %s (%.1fMB)", audio_path, file_size_mb)
            t0 = __import__("time").time()

            resp = requests.post(
                f"{MIMO_ASR_BASE_URL}/chat/completions",
                headers={
                    "api-key": MIMO_API_KEY,
                    "Content-Type": "application/json",
                },
                json={
                    "model": "mimo-v2.5-asr",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_audio",
                                    "input_audio": {
                                        "data": f"data:{mime_type};base64,{audio_base64}"
                                    }
                                }
                            ]
                        }
                    ],
                    "asr_options": {
                        "language": "zh"
                    }
                },
                timeout=120,
            )

            elapsed = __import__("time").time() - t0
            result = resp.json()

            if resp.status_code != 200:
                error_msg = result.get("error", {}).get("message", resp.text[:200])
                logger.error("MiMo ASR error: %s", error_msg)
                return {"success": False, "text": "", "message": f"MiMo ASR 识别失败: {error_msg}", "engine_used": "mimo"}

            text = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            logger.info("MiMo ASR done in %.1fs, text length: %d", elapsed, len(text))

            if not text:
                return {"success": False, "text": "", "message": "MiMo ASR 返回空结果", "engine_used": "mimo"}

            text = _traditional_to_simplified(text)
            text = _restore_punctuation(text)

            # 尝试说话人识别
            try:
                from app.speaker_diarization import SpeakerDiarization
                diarizer = SpeakerDiarization()
                if diarizer.has_resemblyzer and diarizer.has_sklearn:
                    diarization_result = diarizer.diarize(audio_path)
                    if diarization_result:
                        text_with_speakers = self._add_speaker_labels(text, diarization_result)
                        text = text_with_speakers
                        return {"success": True, "text": text, "message": f"MiMo ASR 识别完成 ({elapsed:.1f}s)", "engine_used": "mimo", "diarization": diarization_result}
            except Exception as e:
                logger.warning(f"说话人识别失败，使用原始文本: {e}")

            return {"success": True, "text": text, "message": f"MiMo ASR 识别完成 ({elapsed:.1f}s)", "engine_used": "mimo"}
        except ImportError:
            return {"success": False, "text": "", "message": "缺少 requests 库", "engine_used": "mimo"}
        except Exception as e:
            return {"success": False, "text": "", "message": f"MiMo ASR 异常: {str(e)}", "engine_used": "mimo"}

    def _add_speaker_labels(self, text: str, diarization_result: list) -> str:
        """将说话人标签添加到文本中"""
        if not diarization_result or not text:
            return text
        
        sorted_segments = sorted(diarization_result, key=lambda x: x["start"])
        unique_speakers = set(s["speaker"] for s in sorted_segments)
        
        total_duration = sorted_segments[-1]["end"] - sorted_segments[0]["start"]
        if total_duration <= 0:
            total_duration = 1.0
        
        import re
        sentences = re.split(r'([。！？；\n]+)', text)
        real_sentences = [s for s in sentences if s.strip() and not re.match(r'^[。！？；\n]+$', s)]
        
        if len(real_sentences) <= 1 and len(unique_speakers) <= 1:
            speaker = sorted_segments[0]["speaker"]
            label = f"说话人{speaker.split('_')[1]}" if speaker.startswith("Speaker_") else speaker
            return f"【{label}】{text}"
        
        if len(real_sentences) <= len(sorted_segments):
            result = []
            for i, sent in enumerate(real_sentences):
                seg_idx = min(i, len(sorted_segments) - 1)
                speaker = sorted_segments[seg_idx]["speaker"]
                label = f"说话人{speaker.split('_')[1]}" if speaker.startswith("Speaker_") else speaker
                result.append(f"【{label}】{sent}")
            puncts = re.findall(r'[。！？；\n]+', text)
            for i, p in enumerate(puncts):
                if i < len(result):
                    result[i] += p
            return ''.join(result)
        
        speaker_timeline = []
        for seg in sorted_segments:
            speaker_timeline.append((seg["start"], seg["end"], seg["speaker"]))
        
        result = []
        text_len = len(text)
        used_segments = []
        
        for i, sent in enumerate(real_sentences):
            position_ratio = len(''.join(real_sentences[:i+1])) / text_len
            current_time = sorted_segments[0]["start"] + position_ratio * total_duration
            
            best_speaker = sorted_segments[0]["speaker"]
            best_overlap = 0
            for start, end, speaker in speaker_timeline:
                if start <= current_time <= end:
                    best_speaker = speaker
                    break
                overlap = max(0, min(end, current_time) - max(start, current_time - 1.0))
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_speaker = speaker
            
            if not used_segments or used_segments[-1] != best_speaker:
                label = f"说话人{best_speaker.split('_')[1]}" if best_speaker.startswith("Speaker_") else best_speaker
                result.append(f"【{label}】{sent}")
                used_segments.append(best_speaker)
            else:
                result.append(sent)
        
        puncts = re.findall(r'[。！？；\n]+', text)
        for i, p in enumerate(puncts):
            if i < len(result):
                result[i] += p
        
        return ''.join(result)


speech_recognizer = SpeechRecognizer()
