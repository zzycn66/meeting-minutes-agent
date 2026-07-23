# -*- coding: utf-8 -*-
"""共享正则模式 — 消除 speech_service / nlp_service / streaming_service 之间的重复定义"""
import re

# ── 句子分割 ──
RE_SENT_SPLIT = re.compile(r'[。！？\n]+')

# ── 数字行检测 ──
RE_DIGIT_LINE = re.compile(r'^[\d:：\s]+$')

# ── 人名提取 ──
RE_PERSON_EXTRACT = re.compile(r'([\u4e00-\u9fa5]{2,4})[：:说问道答讲]')

# ── 参会人标签提取 ──
RE_PARTICIPANT_LABEL = re.compile(r'(?:负责人|参会人[员]?|出席|列席|主持)[：:]\s*([\u4e00-\u9fa5、，,\s]{2,30})')

# ── 参会人分割 ──
RE_PARTICIPANT_SPLIT = re.compile(r'[、，,，\s]+')

# ── 人名匹配模式（超集，合并 nlp_service + speech_service）──
PERSON_PATTERNS_SRC = [
    r'(?:由|请|让|安排|指派|交给)([\u4e00-\u9fa5]{2,4}?)(?=[^我你他她它]|$)(?:负责|完成|跟进|处理|来做|落实|调研|开发|设计)',
    r'([\u4e00-\u9fa5]{2,4}?)(?=[^我你他她它]|$)(?:负责|来负责|来完成|来跟进|去调研|去开发)',
    r'@([\u4e00-\u9fa5]{2,4})',
    r'([\u4e00-\u9fa5]{2,4})(?:说|讲|提到|认为|觉得|建议|提议)',
    r'让([\u4e00-\u9fa5]{2,4})',
    r'([\u4e00-\u9fa5]{2,4})(?:我|我们)',
]
RE_PERSON_PATTERNS = [re.compile(p) for p in PERSON_PATTERNS_SRC]

# ── 截止时间匹配模式（超集）──
DEADLINE_PATTERNS_SRC = [
    r'(截止|截止时间|截止日期|deadline)[：:]\s*(.+?)(?:[。；\n]|$)',
    r'(\d+月\d+[日号])',
    r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})',
    r'(下周[一二三四五六日]|本周[一二三四五六日]|下周一|下周二|下周三|下周四|下周五)',
    r'(今天|明天|后天)',
    r'(这周|下周)',
    r'(\d+周)',
    r'(\d+个月)',
    r'(\d+天)',
    r'(\d+号前)',
    r'(\d+月前)',
    r'(月底前?)',
    r'(年底)',
    r'(年前)',
    r'(8月)',
    r'(7月)',
    r'(下个月)',
    r'(这个月)',
]
RE_DEADLINE_PATTERNS = [re.compile(p) for p in DEADLINE_PATTERNS_SRC]

# ── Whisper prompt echo 检测 ──
# 更详细的初始提示，帮助模型理解上下文，提高识别准确率
WHISPER_INITIAL_PROMPT = "以下是一段中文会议录音。参会人员正在讨论产品需求、技术方案、项目进度和工作安排。"
WHISPER_PROMPT_FRAGMENTS = [
    "中文会议录音", "一段中文", "会议录音的文字记录",
    "中文会议", "以下是一段", "文字记录",
    "会议的录音转写", "正式会议",
]


# ── Whisper 幻觉检测（重复文本）──
REPEAT_CHAR = re.compile(r'(.)\1{4,}')  # 单字符重复5次以上
REPEAT_WORD = re.compile(r'(\S{2,6})\1{3,}')  # 2-6字符词重复3次以上
REPEAT_PHRASE = re.compile(r'(.{2,10})\1{2,}')  # 短语重复2次以上


def detect_prompt_echo(text: str) -> bool:
    """检测 Whisper 是否只输出了初始提示词（音频无有效内容）"""
    if not text:
        return True
    if text.strip().rstrip("。") == WHISPER_INITIAL_PROMPT.rstrip("。"):
        return True
    if len(text) < 40 and any(frag in text for frag in WHISPER_PROMPT_FRAGMENTS):
        return True
    return False


def detect_repetition(text: str) -> bool:
    """检测文本中的重复幻觉"""
    if not text or len(text) < 4:
        return False
    if REPEAT_CHAR.search(text):
        return True
    if REPEAT_WORD.search(text):
        return True
    if REPEAT_PHRASE.search(text):
        return True
    return False


# ── faster-whisper 转写参数 ──
WHISPER_TRANSCRIBE_KWARGS = dict(
    language="zh",
    task="transcribe",
    beam_size=5,
    best_of=5,
    temperature=0.0,
    condition_on_previous_text=False,
    initial_prompt=WHISPER_INITIAL_PROMPT,
    vad_filter=True,
    vad_parameters=dict(
        min_silence_duration_ms=500,
        speech_pad_ms=300,
        threshold=0.35,
    ),
)


