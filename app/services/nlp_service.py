# -*- coding: utf-8 -*-
"""
NLP 信息提取服务模块

本模块实现了会议文本的智能信息提取，支持三种处理方式：
1. 关键词规则匹配（NLPProcessor）- 轻量级，无需外部 API
2. DeepSeek AI（DeepSeekNLPProcessor）- 云端大模型，效果最佳
3. 本地 Qwen3（LocalQwenProcessor）- 本地大模型，隐私安全

架构设计：
┌─────────────────────────────────────────────────────────────────┐
│                     NLP 信息提取服务                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐        │
│  │  关键词匹配 │    │  DeepSeek   │    │  本地 Qwen3 │        │
│  │  (jieba)    │    │  (云端API)  │    │  (本地推理) │        │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘        │
│         │                  │                  │                │
│         └──────────────────┼──────────────────┘                │
│                            ▼                                   │
│                   ┌─────────────────┐                         │
│                   │   统一输出格式   │                         │
│                   │   (JSON 结构)   │                         │
│                   └─────────────────┘                         │
└─────────────────────────────────────────────────────────────────┘

功能特性：
- 同音字纠错：修复语音转写中的常见错误
- 智能分句：支持按人名、标点、口语连接词分句
- 信息提取：主题、参会人、讨论要点、决策、行动项、遗留问题
- 降级策略：AI 不可用时自动降级到关键词匹配

依赖库：
- jieba: 中文分词（必需）
- openai: DeepSeek API 调用（可选）
- transformers: Qwen3 本地推理（可选）
- torch: 深度学习框架（可选）
"""
import re
import os
import json
import logging
from typing import Optional
from pathlib import Path

# ==================== 依赖检查 ====================
# 检查 jieba 是否可用（用于中文分词）
try:
    import jieba
    import jieba.posseg as pseg  # 词性标注
    import jieba.analyse  # 关键词提取
    JIEBA_LOADED = True
except ImportError:
    JIEBA_LOADED = False
    print("警告: jieba 未安装，关键词匹配功能不可用")

# 检查 transformers 是否可用（用于 Qwen3 本地推理）
TRANSFORMERS_AVAILABLE = False

logger = logging.getLogger(__name__)

# ==================== 配置加载 ====================
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, HF_ENDPOINT

# ==================== 自定义词典加载 ====================
# 服务目录路径
_SERVICE_DIR = Path(__file__).parent
_MEETING_DICT_PATH = _SERVICE_DIR / "meeting_dict.txt"  # 会议领域专业词典
_HOMOPHONE_DICT_PATH = _SERVICE_DIR / "homophone_dict.json"  # 同音字纠错表

# 加载会议领域专业词典（提高 jieba 对专业术语的识别准确率）
if JIEBA_LOADED and _MEETING_DICT_PATH.exists():
    jieba.load_userdict(str(_MEETING_DICT_PATH))
    logger.info("已加载会议领域专业词典: %s", _MEETING_DICT_PATH)

# 加载同音字纠错表（修复语音转写中的常见错误）
HOMOPHONE_MAP = {}
if _HOMOPHONE_DICT_PATH.exists():
    try:
        with open(_HOMOPHONE_DICT_PATH, "r", encoding="utf-8") as f:
            HOMOPHONE_MAP = json.load(f)
        logger.info("成功加载同音字纠错表，共%d条记录", len(HOMOPHONE_MAP))
    except Exception as e:
        logger.error("加载同音字纠错表失败: %s", e)
else:
    logger.warning("同音字纠错表文件不存在: %s", _HOMOPHONE_DICT_PATH)

# ==================== HuggingFace 镜像配置 ====================
# 设置 HuggingFace 镜像地址（国内用户加速下载）
if HF_ENDPOINT:
    os.environ["HF_ENDPOINT"] = HF_ENDPOINT
    # 强制更新 huggingface_hub 缓存的常量（如果已导入）
    try:
        import huggingface_hub.constants as _hf_const
        _hf_const.HF_ENDPOINT = HF_ENDPOINT
        if hasattr(_hf_const, "ENDPOINT"):
            _hf_const.ENDPOINT = HF_ENDPOINT
    except (ImportError, AttributeError):
        pass


# ==================== 关键词库 ====================
# 用于规则匹配的关键词集合，覆盖会议文本中的各类信息

# 决策类关键词：用于识别会议中做出的决定
DECISION_KEYWORDS = [
    # 正向决策
    "决定", "确定", "同意", "通过", "批准", "拍板", "敲定",
    "定下来", "达成共识", "一致认为", "最终方案",
    # 负向决策（取消/推迟）
    "砍掉", "不做了", "放弃", "推迟", "延后", "搁置",
    # 优先级决策
    "优先做", "先做", "放到v", "保留下次",
    "先不做了", "放到", "评估", "优先级",
    # 序号/总结
    "第一", "第二", "第三", "总结",
    # 观点表达
    "我建议", "我提议", "我觉得", "我认为",
    # 方向类
    "方案", "策略", "方向", "结论",
]

# 行动类关键词：用于识别需要执行的任务
ACTION_KEYWORDS = [
    # 责任分配
    "负责", "由.*完成", "由.*跟进", "安排.*做", "指派",
    # 执行动作
    "落实", "执行", "推进", "下一步",
    "上线", "启动", "搞起来", "搞定",
    # 输出要求
    "出报告", "给结果", "回复.*结果",
    # 时间相关
    "估", "评估", "排期", "开始", "结束",
    # 通用动词
    "补", "做", "搞", "弄", "处理",
    # 技术任务
    "跑数据", "上线", "发布", "部署",
    "绑定", "接入", "对接", "开发",
    "设计", "测试", "联调", "验收",
]

# 人名提取正则模式
PERSON_PATTERNS = [
    # "由/请/让 + 人名 + 负责/完成/..."
    r'(?:由|请|让|安排|指派|交给)([\u4e00-\u9fa5]{2,4}?)(?=[^我你他她它]|$)(?:负责|完成|跟进|处理|来做|落实|调研|开发|设计)',
    # "人名 + 负责/来负责/..."
    r'([\u4e00-\u9fa5]{2,4}?)(?=[^我你他她它]|$)(?:负责|来负责|来完成|来跟进|去调研|去开发)',
    # "@人名"
    r'@([\u4e00-\u9fa5]{2,4})',
    # "人名 + 说/讲/提到/..."
    r'([\u4e00-\u9fa5]{2,4})(?:说|讲|提到|认为|觉得|建议|提议)',
    # "让人名"
    r'让([\u4e00-\u9fa5]{2,4})',
    # "人名 + 我/我们"
    r'([\u4e00-\u9fa5]{2,4})(?:我|我们)',
]

# 截止时间提取正则模式
DEADLINE_PATTERNS = [
    # "截止/截止时间：xxx"
    r'(截止|截止时间|截止日期|deadline)[：:]\s*(.+?)(?:[。；\n]|$)',
    # 具体日期：X月X日
    r'(\d+月\d+[日号])',
    # 完整日期：2024-01-01
    r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})',
    # 相对日期：下周X
    r'(下周[一二三四五六日]|本周[一二三四五六日]|下周一|下周二|下周三|下周四|下周五)',
    # 相对日期：今天/明天/后天
    r'(今天|明天|后天)',
    # 相对日期：这周/下周
    r'(这周|下周)',
    # 时间段
    r'(\d+周)',
    r'(\d+个月)',
    r'(\d+天)',
    # 截止提示
    r'(\d+号前)',
    r'(\d+月前)',
    r'(月底前?)',
    r'(年底)',
    r'(年前)',
    # 月份
    r'(8月)',
    r'(7月)',
    r'(下个月)',
    r'(这个月)',
]

# 主题类关键词：用于识别会议主题
TOPIC_KEYWORDS = [
    "议题", "主题", "议程", "关于", "讨论", "会议主题", "本次会议",
    "今天主要", "主要", "定下来", "做哪几个", "功能", "方案",
    "方向", "版本", "规划",
]

# 问题类关键词：用于识别遗留问题
ISSUE_KEYWORDS = [
    # 问题状态
    "问题", "未解决", "待讨论", "需要进一步", "遗留", "暂缓", "推迟",
    "延后", "搁置", "尚需", "还需", "继续讨论", "下次会议",
    "未确定", "不确定", "待定", "pending", "还需要",
    # 资源问题
    "不够", "不足", "赶不上", "成本", "风险", "瓶颈",
    "服务器", "扩容", "资源", "人力", "工时",
    # 进度问题
    "吃不消", "跟不上", "来不及", "赶不上",
    # 阻塞问题
    "风险", "依赖", "阻塞", "卡点",
]

# 停用词：语音转写中的常见填充词
FILLER_WORDS = {"嗯", "啊", "呃", "那个", "这个", "然后", "就是说", "对吧", "是吧"}
# 噪声模式：纯数字行、纯标点行
NOISE_PATTERNS = [re.compile(p) for p in [r'^\d+$', r'^[，,。.！!？?]+$']]

# ==================== 正则表达式导入 ====================
# 从共享模块导入重复使用的正则模式（避免重复定义）
from app.utils.regex_patterns import (
    RE_SENT_SPLIT as _RE_SENT_SPLIT,  # 句子分割正则
    RE_DIGIT_LINE as _RE_DIGIT_LINE,  # 纯数字行检测
    RE_PERSON_EXTRACT as _RE_PERSON_EXTRACT,  # 人名提取
    RE_PARTICIPANT_LABEL as _RE_PARTICIPANT_LABEL,  # 参会人标签
    RE_PARTICIPANT_SPLIT as _RE_PARTICIPANT_SPLIT,  # 参会人分割
    RE_PERSON_PATTERNS as _RE_PERSON_PATTERNS,  # 人名模式
    RE_DEADLINE_PATTERNS as _RE_DEADLINE_PATTERNS,  # 截止时间模式
)

# ==================== 本模块独有正则 ====================
# 多换行符合并（3个以上换行符合并为2个）
_RE_NEWLINE3 = re.compile(r'\n{3,}')
# 中文人名校验（2-4个汉字）
_RE_PERSON_CHECK = re.compile(r'^[\u4e00-\u9fa5]{2,4}$')

# ==================== 热路径预编译正则 ====================
# 用于文本清洗和分割的高频正则，预先编译提高性能

# 多逗号合并：将连续的逗号替换为句号
_RE_MULTI_COMMA = re.compile(r'[，,]{2,}')
# 句子边界检测：在句号/感叹号/问号后分割
_RE_SENT_BOUNDARY = re.compile(r'(?<=[。！？])\s*(?=[^\s])')
# 分号/顿号分割：用于长句分割
_RE_SPLICE_SEMICOLON = re.compile(r'[；;、]')
# 逗号后分割：用于超长句进一步分割
_RE_SPLICE_COMMA = re.compile(r'(?<=[，,])')
# 多标点合并：清理连续的标点符号
_RE_SPLICE_DOUBLE = re.compile(r'[，,；;、]{2,}')

# 跳过词：不参与人名识别的常见词汇
_SKIP_WORDS = {
    # 通用词汇
    "会议", "我们", "他们", "大家", "这个", "那个", "今天", "明天", "现在",
    "然后", "所以", "因为", "但是", "可以", "需要", "应该", "已经", "问题",
    "如果", "就是", "或者", "还有", "什么", "怎么", "这样", "那样",
    # 部门/职能
    "产品", "技术", "项目", "设计", "运营", "市场", "销售", "财务",
    "部门", "公司", "团队", "系统", "功能", "需求", "方案", "计划",
    "时间", "地点", "内容", "目标", "结果", "情况", "讨论",
}

# ==================== 关键词合并正则 ====================
# 将关键词列表合并为单个正则表达式，避免逐个 re.search 提高性能
_ACTION_KW_RE = re.compile("|".join(re.escape(kw) for kw in ACTION_KEYWORDS))
_DECISION_KW_RE = re.compile("|".join(re.escape(kw) for kw in DECISION_KEYWORDS))
_TOPIC_KW_RE = re.compile("|".join(re.escape(kw) for kw in TOPIC_KEYWORDS))
_ISSUE_KW_RE = re.compile("|".join(re.escape(kw) for kw in ISSUE_KEYWORDS))
# 人名提取正则列表
_RE_PERSON_PATTERNS = [re.compile(p) for p in PERSON_PATTERNS]
# 截止时间提取正则列表
_RE_DEADLINE_PATTERNS = [re.compile(p) for p in DEADLINE_PATTERNS]

# ==================== 公共常量 ====================
# 非人名词汇：这些词汇虽然可能是2-4个汉字，但不是人名
_NOT_PERSON_WORDS = {
    # 代词
    "我们", "你们", "他们", "大家", "自己", "别人", "谁", "什么",
    "我", "你", "他", "她", "它", "这", "那", "哪",
    # 称谓
    "各位", "所有人", "对方", "本人", "还有个", "那个", "这个",
    # 时间词
    "今天", "明天", "现在", "然后", "所以", "因为", "但是",
    # 动词/形容词
    "可以", "需要", "应该", "已经", "如果", "就是", "或者",
    "还有", "怎么", "这样", "那样",
    # 部门/职能
    "产品", "技术", "项目", "设计", "运营", "市场", "销售", "财务",
    "部门", "公司", "团队", "系统", "功能", "需求", "方案", "计划",
    "时间", "地点", "内容", "目标", "结果", "情况", "讨论", "问题",
    # 业务术语
    "智能", "推荐", "算法", "社交", "分享", "会员", "积分",
    "体系", "前端", "后端", "数据", "用户", "调研", "竞品",
    "分析", "方向", "上线", "优化", "重构", "组件", "升级",
    "安卓", "iOS", "上个月", "下个月", "这个月",
    # 语气词
    "好", "那", "行", "对", "嗯", "啊", "呃",
    # 版本/功能
    "版本", "功能", "优先", "砍掉", "不做了", "放到", "下次",
    # 资源相关
    "人力", "工时", "评估", "周期", "资源", "成本", "预算",
    "服务器", "扩容", "数据", "埋点", "采集", "清洗", "算法",
    "调优", "上线", "节奏", "规划", "活动", "投放", "素材",
    # 营销相关
    "注册", "送", "积分", "转化率", "感知", "福利", "一眼",
    # 界面相关
    "设计稿", "风格", "个人中心", "任务", "入口", "重叠",
    "统一", "整块", "改版", "反攻", "接口", "临时", "评论区",
    # 观点表达
    "总结", "一下", "来说", "认为", "觉得", "建议", "提议",
    # 动作词汇
    "负责", "完成", "跟进", "处理", "来做", "落实", "调研",
    "开发", "设计", "测试", "联调", "验收", "部署", "发布",
    # 项目管理
    "需求", "评审", "排期", "迭代", "版本", "上线", "回滚",
    "灰度", "热修复", "监控", "报警", "告警", "故障", "事故",
    "周报", "日报", "月报", "OKR", "KPI", "优先级", "紧急",
    "P0", "P1", "P2", "P3", "bug", "缺陷",
    # 技术术语
    "前端", "后端", "客户端", "服务端", "数据库", "缓存",
    "消息队列", "微服务", "API", "接口", "SDK", "组件", "模块",
    "插件", "中间件", "框架", "平台", "系统", "服务", "产品",
    # 职能部门
    "运营", "市场", "销售", "财务", "法务", "UED", "UI", "UX",
    "交互", "视觉", "设计稿", "原型", "PRD", "MRD", "BRD",
    # 敏捷术语
    "用户故事", "验收标准", "敏捷", "Scrum", "看板", "站会",
    "评审会", "复盘会", "需求会",
}

# 口语连接词：用于识别口语化的句子边界
_ORAL_CONNECTORS = [
    # 转折/承接
    "然后", "那么", "所以", "但是", "另外", "还有", "接下来", "下一步",
    "而且", "不过", "其实", "说实话", "对吧", "是吧", "就说",
    # 发言人标记
    "我先说", "你先说", "他先说", "她先说",
    # 观点表达
    "我觉得", "我认为", "我建议", "我提议",
    # 序号
    "第一", "第二", "第三", "首先", "其次", "最后",
    # 语气词
    "好", "行", "对", "嗯", "啊", "呃",
    "那", "这个", "那个", "就是说",
    # 插话/补充
    "插一句", "补充一下", "说一下", "提一下",
]
# 将口语连接词合并为正则模式
_ORAL_PATTERN = "|".join(re.escape(conn) for conn in _ORAL_CONNECTORS)

# ==================== 预编译的模式匹配正则 ====================
# 用于复杂模式匹配的复合正则表达式

# 决策模式正则：匹配各种决策表达
_DECISION_PATTERNS_RE = re.compile("|".join([
    r'(?:决定|确定|同意|通过|批准|拍板|敲定|定下来)',  # 正向决策
    r'(?:砍掉|不做了|放弃|推迟|延后|搁置)',  # 负向决策
    r'(?:优先做|先做|放到|保留下次)',  # 优先级决策
    r'(?:先不做了|放到.*?评估)',  # 推迟决策
    r'(?:第一|第二|第三).*?(?:方案|策略|方向)',  # 序号决策
    r'(?:我建议|我提议|我觉得|我认为).*?(?:优先|先做|先不做)',  # 观点决策
    r'(?:方案|策略|方向|结论).*?(?:是|为|：)',  # 方向决策
]))

# 行动模式正则：匹配各种行动表达
_ACTION_PATTERNS_RE = re.compile("|".join([
    r'(?:负责|由.*?完成|由.*?跟进|安排.*?做|指派)',  # 责任分配
    r'(?:落实|执行|推进|下一步)',  # 执行动作
    r'(?:上线|启动|搞起来|搞定)',  # 启动动作
    r'(?:出报告|给结果|回复.*?结果)',  # 输出要求
    r'(?:估|评估|排期|开始|结束)',  # 时间相关
    r'(?:补|做|搞|弄|处理)',  # 通用动词
    r'(?:跑数据|上线|发布|部署)',  # 技术任务
    r'(?:绑定|接入|对接|开发)',  # 集成任务
    r'(?:设计|测试|联调|验收)',  # 流程任务
    r'(?:让|请|安排).*?(?:负责|完成|跟进|处理|来做|落实|调研|开发|设计)',  # 委托任务
    r'(?:我|我们).*?(?:负责|完成|跟进|处理|来做|落实|调研|开发|设计)',  # 自主任务
]))

# 问题模式正则：匹配各种问题表达
_ISSUE_PATTERNS_RE = re.compile("|".join([
    r'(?:问题|未解决|待讨论|需要进一步|遗留|暂缓|推迟)',  # 问题状态
    r'(?:延后|搁置|尚需|还需|继续讨论|下次会议)',  # 待处理
    r'(?:未确定|不确定|待定|pending|还需要)',  # 未确定
    r'(?:不够|不足|赶不上|成本|风险|瓶颈)',  # 资源问题
    r'(?:服务器|扩容|资源|人力|工时)',  # 资源限制
    r'(?:吃不消|跟不上|来不及|赶不上)',  # 进度问题
    r'(?:依赖|阻塞|卡点)',  # 阻塞问题
    r'(?:数据.*?不够|埋点.*?不够|采集.*?不够)',  # 数据问题
    r'(?:服务器.*?扩容|成本.*?多)',  # 基础设施问题
]))


class NLPProcessor:
    """
    基于 jieba 分词的关键词+规则匹配处理器

    这是最基础的 NLP 处理器，不依赖外部 API，完全本地运行。
    适用于：
    - 无法访问外部 API 的场景
    - 需要快速处理的场景
    - 作为 AI 处理器的降级方案

    核心功能：
    1. 同音字纠错：修复语音转写中的常见错误
    2. 智能分句：支持按人名、标点、口语连接词分句
    3. 信息提取：主题、参会人、讨论要点、决策、行动项、遗留问题

    使用示例：
        processor = NLPProcessor()
        result = processor.process("会议文本...")
    """

    def __init__(self):
        """
        初始化 NLP 处理器

        将关键词和专业术语添加到 jieba 词典中，
        提高分词和词性标注的准确率。
        """
        self.jieba_loaded = JIEBA_LOADED
        if JIEBA_LOADED:
            # 将各类关键词添加到 jieba 词典
            for w in DECISION_KEYWORDS + ACTION_KEYWORDS + TOPIC_KEYWORDS + ISSUE_KEYWORDS:
                jieba.add_word(w)
            # 添加常见人名（高频词，提高识别率）
            for w in ["张三", "李四", "王五", "赵六", "负责人", "参会人", "主持人"]:
                jieba.add_word(w, freq=10000, tag="nr")  # nr = 人名

            # 添加会议领域专业术语
            meeting_terms = [
                # 业务术语
                "智能推荐", "算法升级", "社交分享", "积分体系", "会员体系",
                "数据埋点", "数据采集", "数据清洗", "竞品分析", "用户调研",
                "转化率", "分享率", "留存率", "拉新", "拉新活动", "促活",
                "投放", "素材", "预算", "排期", "里程碑", "交付物", "复盘",
                # 互联网黑话
                "对齐", "拉齐", "赋能", "抓手", "闭环", "链路", "心智",
                # 规划相关
                "版本规划", "功能规划", "产品规划", "技术方案", "架构设计",
                # 评审相关
                "评审", "需求评审", "设计评审", "代码评审", "测试用例",
                # 测试相关
                "回归测试", "压力测试", "性能测试", "灰度发布", "全量上线",
                # 运维相关
                "回滚", "热修复", "监控", "报警", "告警", "故障", "事故",
                # 项目管理
                "周报", "日报", "月报", "OKR", "KPI", "优先级", "紧急",
                "P0", "P1", "P2", "P3", "bug", "缺陷", "需求", "功能",
                # 版本号
                "迭代", "版本", "v3.2", "v4.0",
                # 技术术语
                "前端", "后端", "客户端", "服务端", "数据库", "缓存",
                "消息队列", "微服务", "API", "接口", "SDK", "组件", "模块",
                "插件", "中间件", "框架", "平台", "系统", "服务", "产品",
                # 职能部门
                "运营", "市场", "销售", "财务", "法务", "UED", "UI", "UX",
                "交互", "视觉", "设计稿", "原型", "PRD", "MRD", "BRD",
                # 敏捷术语
                "用户故事", "验收标准", "敏捷", "Scrum", "看板", "站会",
                "评审会", "复盘会", "需求会",
            ]
            for term in meeting_terms:
                jieba.add_word(term, freq=10000, tag="n")  # n = 名词

    def _correct_homophone(self, text: str) -> str:
        """
        同音字纠错

        基于预定义的纠错表修复语音转写中的常见错误。
        例如："张三说" 可能被转写为 "张三缩"

        Args:
            text (str): 原始文本

        Returns:
            str: 纠错后的文本
        """
        if not HOMOPHONE_MAP:
            return text
        for wrong, correct in HOMOPHONE_MAP.items():
            text = text.replace(wrong, correct)
        return text

    def _tokenize(self, text: str) -> list:
        """
        中文分词

        使用 jieba 进行中文分词，并过滤停用词。

        Args:
            text (str): 输入文本

        Returns:
            list: 分词结果列表
        """
        if not self.jieba_loaded:
            return list(text)
        # 先进行同音字纠错
        text = self._correct_homophone(text)
        # 分词并过滤空格和停用词
        return [w for w in jieba.cut(text) if w.strip() and w not in FILLER_WORDS]

    def _tokenize_set(self, text: str) -> set:
        """分词并返回集合（用于快速查找）"""
        return set(self._tokenize(text))

    def _detect_speakers(self, text: str) -> list:
        """
        说话人检测

        全文扫描，返回所有疑似人名。
        使用两种策略：
        1. 词性标注（POS）：识别 jieba 标注为"nr"（人名）的词
        2. 位置启发式：在句首/句尾出现的2-4字词可能是人名

        Args:
            text (str): 输入文本

        Returns:
            list: 疑似人名列表，按出现顺序排列

        Example:
            >>> _detect_speakers("张三说：项目进度正常。李四补充：下周上线。")
            ["张三", "李四"]
        """
        if not self.jieba_loaded:
            return []
        text = self._correct_homophone(text)
        speakers = []
        _PRONOUN_CHARS = set("我你他她它")  # 代词字符，排除含代词的词
        seen = set()  # 去重集合

        # 策略1：词性标注识别
        for word, flag in pseg.cut(text):
            if flag == "nr" and 2 <= len(word) <= 4:  # nr = 人名，2-4个字
                # 排除非人名词汇
                if word in _NOT_PERSON_WORDS or word in FILLER_WORDS or word in _SKIP_WORDS:
                    continue
                # 排除含代词的词
                if any(ch in _PRONOUN_CHARS for ch in word):
                    continue
                # 校验格式并去重
                if _RE_PERSON_CHECK.match(word) and word not in seen:
                    seen.add(word)
                    speakers.append(word)

        # 策略2：位置启发式识别
        pos_set = set(speakers)  # 已识别的人名集合
        _VERB_CHARS = set("说讲问答来去做好行对开看搞定安排负责跟进插总结建议请让")  # 动词字符

        # 查找所有2-3个汉字的词
        for m in re.finditer(r'([\u4e00-\u9fa5]{2,3})', text):
            c = m.group(1)
            # 排除非人名词汇
            if c in _NOT_PERSON_WORDS or c in _SKIP_WORDS or c in FILLER_WORDS:
                continue
            if any(ch in _PRONOUN_CHARS for ch in c):
                continue
            if not _RE_PERSON_CHECK.match(c):
                continue
            if c in seen:
                continue

            # 检查是否在句子边界
            end = m.end()
            before = text[m.start()-1:m.start()] if m.start() > 0 else ""
            after = text[end:end+1]
            # 句首/句尾/标点后 是边界
            at_boundary = (not before or before in "。！？：:\n ") or (after in "，,。！？：:\n " or not after)

            # 边界处 + 后面是动词 或 已在人名集合中
            if at_boundary and (after in _VERB_CHARS or c in pos_set):
                seen.add(c)
                speakers.append(c)

        return speakers

    def preprocess(self, text: str) -> str:
        """
        文本预处理

        对原始文本进行清洗和规范化：
        1. 同音字纠错
        2. 统一换行符
        3. 合并多余空行
        4. 过滤噪声行（纯数字、纯标点）

        Args:
            text (str): 原始文本

        Returns:
            str: 清洗后的文本
        """
        # 先进行同音字纠错
        text = self._correct_homophone(text)
        # 统一换行符（Windows/Unix）
        text = re.sub(r'\r\n|\r', '\n', text)
        # 合并3个以上连续换行符为2个
        text = _RE_NEWLINE3.sub('\n\n', text)
        # 分割行并清洗
        lines = [l.strip() for l in text.split('\n')]
        # 过滤空行和噪声行
        lines = [l for l in lines if l and not any(p.match(l) for p in NOISE_PATTERNS)]
        return '\n'.join(lines).strip()

    def _split_raw_oral(self, text: str) -> list:
        """
        原始语音转写文本分句

        按检测到的人名位置直接切分原文。
        适用于口语化的语音转写文本。

        Args:
            text (str): 原始语音转写文本

        Returns:
            list: 分句结果列表

        Example:
            >>> _split_raw_oral("张三说项目进度正常李四说下周上线")
            ["张三说项目进度正常", "李四说下周上线"]
        """
        # 检测说话人
        speakers = self._detect_speakers(text)
        if not speakers:
            return self._split_by_punctuation(text)

        # 查找所有人名出现的位置
        positions = []
        for m in re.finditer(r'([\u4e00-\u9fa5]{2,3})', text):
            c = m.group(1)
            if c not in speakers:
                continue
            # 检查是否在句子边界
            before = text[m.start()-1:m.start()] if m.start() > 0 else ""
            after = text[m.end():m.end()+1]
            at_boundary = (
                (not before or before in "。！？：:\n ") or
                (after in "，,。！？：:\n " or not after)
            )
            if at_boundary:
                positions.append((m.start(), c))

        # 人名位置不足2个，降级到标点分句
        if len(positions) < 2:
            return self._split_by_punctuation(text)

        # 按人名位置切分文本
        result = []
        for i, (pos, name) in enumerate(positions):
            end = positions[i+1][0] if i+1 < len(positions) else len(text)
            segment = text[pos:end].strip()
            # 对每个片段再按标点分句
            sub = self._split_by_punctuation(segment)
            result.extend(sub)
        return result

    def _split_by_punctuation(self, text: str, _corrected: bool = False) -> list:
        """
        按标点和口语连接词分句

        多层次分句策略：
        1. 合并连续逗号为句号
        2. 在口语连接词处插入句号
        3. 在句子边界处分割
        4. 对长句进一步分割（分号、顿号、逗号）

        Args:
            text (str): 输入文本
            _corrected (bool): 是否已进行同音字纠错

        Returns:
            list: 分句结果列表
        """
        if not _corrected:
            text = self._correct_homophone(text)
        # 合并连续逗号为句号
        text = _RE_MULTI_COMMA.sub('。', text)
        # 在口语连接词处插入句号
        text = re.sub(rf'(?:{_ORAL_PATTERN})', '。', text)
        # 在句子边界处分割
        text = _RE_SENT_BOUNDARY.sub('\n', text)
        # 按句子分割正则切分
        raw = _RE_SENT_SPLIT.split(text)

        sentences = []
        for s in raw:
            s = s.strip()
            # 过滤太短的句子
            if len(s) < 3:
                continue
            # 过滤纯数字行
            if _RE_DIGIT_LINE.match(s):
                continue
            # 长句进一步分割
            if len(s) > 60:
                # 按分号/顿号分割
                sub = _RE_SPLICE_SEMICOLON.split(s)
                for p in sub:
                    p = p.strip()
                    if len(p) >= 3:
                        # 超长句再按逗号分割
                        if len(p) > 80:
                            sub2 = _RE_SPLICE_COMMA.split(p)
                            sentences.extend(pp.strip() for pp in sub2 if len(pp.strip()) >= 3)
                        else:
                            sentences.append(p)
            else:
                sentences.append(s)
        return sentences

    def split_sentences(self, text: str, _corrected: bool = False) -> list:
        """
        智能分句

        分句策略：
        1. 先尝试按人名切分（适用于有明确说话人的文本）
        2. 如果人名切分效果不好，降级到标点切分

        Args:
            text (str): 输入文本
            _corrected (bool): 是否已进行同音字纠错

        Returns:
            list: 分句结果列表

        Example:
            >>> split_sentences("张三说项目正常。李四说下周上线。")
            ["张三说项目正常。", "李四说下周上线。"]
        """
        if not _corrected:
            text = self._correct_homophone(text)
        # 尝试按人名切分
        oral_result = self._split_raw_oral(text)
        # 如果切分出3个以上句子，采用人名切分结果
        if len(oral_result) >= 3:
            return oral_result

        # 降级到标点切分
        raw = _RE_SENT_SPLIT.split(text)
        sentences = []
        for s in raw:
            s = s.strip()
            if len(s) < 3:
                continue
            if _RE_DIGIT_LINE.match(s):
                continue
            # 长句进一步分割
            if len(s) > 80:
                parts = _RE_SPLICE_DOUBLE.split(s)
                sentences.extend(p.strip() for p in parts if len(p.strip()) >= 3)
            else:
                sentences.append(s)
        return sentences

    def _sentence_has_keywords(self, sent: str, kw_re) -> bool:
        """
        检查句子是否包含关键词

        两种检查方式：
        1. 直接正则匹配
        2. 分词后匹配（更准确）

        Args:
            sent (str): 输入句子
            kw_re (re.Pattern): 关键词正则表达式

        Returns:
            bool: 是否包含关键词
        """
        # 直接正则匹配
        if kw_re.search(sent):
            return True
        # 分词后匹配（更准确）
        if self.jieba_loaded:
            for tok in jieba.cut(sent):
                if kw_re.search(tok):
                    return True
        return False

    def _extract_persons_by_pos(self, sent: str) -> list:
        """
        通过词性标注提取人名

        使用 jieba 的词性标注功能，识别标注为"nr"（人名）的词。

        Args:
            sent (str): 输入句子

        Returns:
            list: 人名列表
        """
        if not self.jieba_loaded:
            return []
        persons = []
        _PRONOUN_CHARS = set("我你他她它")
        for word, flag in pseg.cut(sent):
            if flag == "nr" and 2 <= len(word) <= 4:
                if word in _NOT_PERSON_WORDS or word in FILLER_WORDS or word in _SKIP_WORDS:
                    continue
                if any(ch in _PRONOUN_CHARS for ch in word):
                    continue
                if _RE_PERSON_CHECK.match(word):
                    persons.append(word)
        return persons

    def extract_topic(self, text: str, given_title: str = "", _corrected: bool = False) -> str:
        """
        提取会议主题

        优先级：
        1. 匹配特定模式（"今天主要..."、"定下来..."）
        2. 包含主题关键词的句子
        3. jieba 关键词提取
        4. 返回第一句话

        Args:
            text (str): 会议文本
            given_title (str): 给定的标题（可选）
            _corrected (bool): 是否已进行同音字纠错

        Returns:
            str: 会议主题（最多120字符）
        """
        if not _corrected:
            text = self._correct_homophone(text)
        sentences = self.split_sentences(text, _corrected=True)

        # 策略1：匹配特定模式
        topic_patterns = [
            r'今天主要.*?(?:定下来|做|讨论|确定)',
            r'(?:定下来|确定|讨论).*?(?:功能|方案|方向|版本)',
            r'(?:v\d+\.\d+|版本).*?(?:做|包含|包括).*?(?:功能|特性)',
        ]
        for pattern in topic_patterns:
            for sent in sentences[:10]:
                match = re.search(pattern, sent)
                if match:
                    return match.group(0)[:120]

        # 策略2：包含主题关键词的句子
        for sent in sentences[:5]:
            if self._sentence_has_keywords(sent, _TOPIC_KW_RE):
                return sent.strip()[:120]

        # 策略3：jieba 关键词提取
        if self.jieba_loaded and sentences:
            tags = jieba.analyse.extract_tags(text, topK=5)
            topic_tags = [t for t in tags if t not in FILLER_WORDS and t not in _SKIP_WORDS]
            if topic_tags:
                return "、".join(topic_tags[:3])

        # 策略4：返回第一句话
        return sentences[0][:120] if sentences else "会议记录"

    def extract_overview(self, text: str, _corrected: bool = False) -> str:
        """
        提取会议概述

        取前4个句子作为概述。

        Args:
            text (str): 会议文本
            _corrected (bool): 是否已进行同音字纠错

        Returns:
            str: 会议概述
        """
        sentences = self.split_sentences(text, _corrected=_corrected)
        if len(sentences) <= 4:
            return "；".join(sentences)
        return "。".join(sentences[:4]) + "。"

    def extract_discussion_points(self, text: str, _corrected: bool = False) -> str:
        """
        提取讨论要点

        策略：
        1. 包含主题关键词的句子
        2. 使用 jieba 关键词提取评分

        Args:
            text (str): 会议文本
            _corrected (bool): 是否已进行同音字纠错

        Returns:
            str: 讨论要点列表（每行以•开头）
        """
        sentences = self.split_sentences(text, _corrected=_corrected)
        points = []
        # 策略1：包含主题关键词的句子
        for sent in sentences:
            if self._sentence_has_keywords(sent, _TOPIC_KW_RE) and len(sent) > 8:
                points.append(sent)
        # 策略2：关键词提取评分
        if not points and len(sentences) > 3:
            if self.jieba_loaded:
                scored = []
                for s in sentences[1:-1]:
                    if len(s) > 10:
                        tags = jieba.analyse.extract_tags(s, topK=2)
                        scored.append((len(tags), s))
                scored.sort(key=lambda x: x[0], reverse=True)
                points = [s for _, s in scored[:8]]
            else:
                points = [s for s in sentences[1:-1] if len(s) > 10][:8]
        if points:
            return "\n".join([f"• {p}" for p in points])
        return "详见会议原始记录"

    def extract_key_decisions(self, text: str, _corrected: bool = False) -> str:
        """
        提取关键决策

        识别会议中做出的决策，排除问题类句子。

        Args:
            text (str): 会议文本
            _corrected (bool): 是否已进行同音字纠错

        Returns:
            str: 关键决策列表（每行以•开头）
        """
        if not _corrected:
            text = self._correct_homophone(text)
        sentences = self.split_sentences(text, _corrected=True)
        decisions = []
        for sent in sentences:
            # 排除问题类句子
            if self._sentence_has_keywords(sent, _ISSUE_KW_RE):
                continue
            # 匹配决策关键词或模式
            if self._sentence_has_keywords(sent, _DECISION_KW_RE) or _DECISION_PATTERNS_RE.search(sent):
                cleaned = re.sub(r'^[，,。.！!？?\s]+', '', sent)
                if cleaned and len(cleaned) > 5:
                    decisions.append(cleaned)
        if decisions:
            return "\n".join([f"• {d}" for d in decisions])
        return "会议中未明确记录关键决策"

    def extract_action_items(self, text: str, _corrected: bool = False) -> list:
        """
        提取行动项

        识别需要执行的任务，包括：
        - 任务内容
        - 负责人
        - 截止时间
        - 优先级

        Args:
            text (str): 会议文本
            _corrected (bool): 是否已进行同音字纠错

        Returns:
            list: 行动项列表，每个元素为字典：
                - content: 任务内容
                - responsible_person: 负责人
                - deadline: 截止时间
                - priority: 优先级
        """
        if not _corrected:
            text = self._correct_homophone(text)
        sentences = self.split_sentences(text, _corrected=True)
        items = []
        seen = set()
        _PRONOUN_CHARS = set("我你他她它")
        _SKIP_PERSON_PREFIXES = {"我", "你", "他", "她", "它", "我们", "你们", "他们"}

        for sent in sentences:
            # 检查是否包含行动关键词
            if not self._sentence_has_keywords(sent, _ACTION_KW_RE) and not _ACTION_PATTERNS_RE.search(sent):
                continue

            # 提取负责人
            person = ""
            for pattern in _RE_PERSON_PATTERNS:
                match = pattern.search(sent)
                if match:
                    for g in match.groups():
                        if g and _RE_PERSON_CHECK.match(g) and not any(ch in _PRONOUN_CHARS for ch in g):
                            if g not in _SKIP_PERSON_PREFIXES:
                                person = g
                                break
                    if person:
                        break
            # 降级：通过词性标注提取
            if not person:
                pos_persons = self._extract_persons_by_pos(sent)
                if pos_persons:
                    for p in pos_persons:
                        if p not in _SKIP_PERSON_PREFIXES:
                            person = p
                            break

            # 提取截止时间
            deadline = ""
            for pattern in _RE_DEADLINE_PATTERNS:
                match = pattern.search(sent)
                if match:
                    deadline = match.group(0)
                    deadline = re.sub(r'^(截止|截止时间|截止日期|deadline)[：:]\s*', '', deadline)
                    break

            # 清洗内容
            cleaned = re.sub(r'^[，,。.！!？?\s]+', '', sent)
            cleaned = re.sub(r'[，,。.！!？?\s]+$', '', cleaned)
            if not cleaned or len(cleaned) < 8:
                continue

            # 过滤无意义内容
            skip_content_words = {"好", "行", "对", "嗯", "啊", "呃", "可以", "没问题", "好的", "明白", "知道了"}
            if cleaned in skip_content_words:
                continue

            # 去重
            key = (person, cleaned[:30])
            if key in seen:
                continue
            seen.add(key)
            items.append({
                "content": cleaned,
                "responsible_person": person,
                "deadline": deadline,
                "priority": "medium"
            })
        return items

    def extract_unresolved_issues(self, text: str, _corrected: bool = False) -> str:
        """
        提取遗留问题

        识别会议中未解决的问题和待讨论事项。

        Args:
            text (str): 会议文本
            _corrected (bool): 是否已进行同音字纠错

        Returns:
            str: 遗留问题列表（每行以•开头）
        """
        if not _corrected:
            text = self._correct_homophone(text)
        sentences = self.split_sentences(text, _corrected=True)
        issues = []
        for sent in sentences:
            if self._sentence_has_keywords(sent, _ISSUE_KW_RE) or _ISSUE_PATTERNS_RE.search(sent):
                cleaned = re.sub(r'^[，,。.！!？?\s]+', '', sent)
                if cleaned and len(cleaned) > 5:
                    issues.append(cleaned)
        if issues:
            return "\n".join([f"• {i}" for i in issues])
        return "无明确遗留问题记录"

    def extract_participants(self, text: str, _corrected: bool = False) -> str:
        """
        提取参会人员

        多策略提取：
        1. 匹配"参会人员："标签
        2. 说话人检测
        3. 人名提取正则
        4. 词性标注

        Args:
            text (str): 会议文本
            _corrected (bool): 是否已进行同音字纠错

        Returns:
            str: 参会人员列表（顿号分隔）
        """
        if not _corrected:
            text = self._correct_homophone(text)
        persons = set()
        _PRONOUN_CHARS = set("我你他她它")

        # 策略1：匹配"参会人员："标签
        m = _RE_PARTICIPANT_LABEL.search(text)
        if m:
            for name in _RE_PARTICIPANT_SPLIT.split(m.group(1)):
                name = name.strip()
                if 2 <= len(name) <= 4 and _RE_PERSON_CHECK.match(name):
                    if name not in _NOT_PERSON_WORDS:
                        persons.add(name)

        # 策略2：说话人检测
        for name in self._detect_speakers(text):
            if name not in _NOT_PERSON_WORDS and not any(ch in _PRONOUN_CHARS for ch in name):
                persons.add(name)

        # 策略3：人名提取正则
        for sent in self.split_sentences(text, _corrected=True)[:30]:
            for p in _RE_PERSON_EXTRACT.finditer(sent):
                name = p.group(1)
                if _RE_PERSON_CHECK.match(name) and name not in _SKIP_WORDS and name not in _NOT_PERSON_WORDS:
                    if not any(ch in _PRONOUN_CHARS for ch in name):
                        persons.add(name)

        # 策略4：词性标注
        if self.jieba_loaded:
            for word, flag in pseg.cut(text):
                if flag == "nr" and 2 <= len(word) <= 4 and word not in _SKIP_WORDS and word not in _NOT_PERSON_WORDS:
                    if not any(ch in _PRONOUN_CHARS for ch in word):
                        persons.add(word)

        return "、".join(persons) if persons else ""

    def generate_summary(self, text: str, decisions: str, action_items: list, issues: str, _corrected: bool = False) -> str:
        if not _corrected:
            text = self._correct_homophone(text)
        parts = []
        if decisions and "未明确记录" not in decisions:
            d_count = len([d for d in decisions.split('\n') if d.strip().startswith('•')])
            if d_count > 0:
                first_d = decisions.split('\n')[0].replace('• ', '').strip()
                # 清理决策内容，去掉开头的标点和语气词
                first_d = re.sub(r'^[，,。.！!？?\s]+', '', first_d)
                if first_d:
                    parts.append(f"会议形成{d_count}项关键决策，核心是：{first_d[:60]}")
        if action_items:
            parts.append(f"明确{len(action_items)}项后续行动")
            for i, item in enumerate(action_items[:3]):
                who = f"（{item['responsible_person']}）" if item.get('responsible_person') else ""
                when = f"，{item['deadline']}" if item.get('deadline') else ""
                short_content = item['content'][:40]
                # 清理行动项内容，去掉开头的标点和语气词
                short_content = re.sub(r'^[，,。.！!？?\s]+', '', short_content)
                if short_content:
                    parts.append(f"  {i+1}. {short_content}{who}{when}")
        if issues and "无明确" not in issues:
            i_count = len([i for i in issues.split('\n') if i.strip().startswith('•')])
            if i_count > 0:
                parts.append(f"遗留{i_count}个待解决问题需后续跟进")
        if not parts:
            return "会议纪要已整理完成，请查看详细内容。"
        return "\n".join(parts)

    def _group_segments_by_speaker(self, text: str) -> list:
        """将文本按发言人分成若干块，每块是该发言人的连续内容"""
        speakers = self._detect_speakers(text)
        if not speakers:
            return [text]

        positions = []
        for m in re.finditer(r'([\u4e00-\u9fa5]{2,3})', text):
            c = m.group(1)
            if c not in speakers:
                continue
            before = text[m.start()-1:m.start()] if m.start() > 0 else ""
            after = text[m.end():m.end()+1]
            at_boundary = (
                (not before or before in "。！？：:\n ") or
                (after in "，,。！？：:\n " or not after)
            )
            if at_boundary:
                positions.append(m.start())

        if len(positions) < 2:
            return [text]

        segments = []
        for i in range(len(positions)):
            start = positions[i]
            end = positions[i+1] if i+1 < len(positions) else len(text)
            seg = text[start:end].strip()
            if seg:
                segments.append(seg)
        return segments

    def process(self, text: str, title: str = "", participants: str = "", max_tokens: int = 0, template_structure: str = None) -> dict:
        clean_text = self.preprocess(text)

        segments = self._group_segments_by_speaker(clean_text)
        all_decisions = []
        all_action_items = []
        all_issues = []
        all_points = []

        for seg in segments:
            block = _RE_MULTI_COMMA.sub('。', seg)
            block = re.sub(rf'(?:{_ORAL_PATTERN})', '。', block)
            block_sents = [s.strip() for s in re.split(r'[。！？；;\n]+', block) if len(s.strip()) >= 3]

            for sent in block_sents:
                is_issue = self._sentence_has_keywords(sent, _ISSUE_KW_RE)
                if is_issue:
                    if sent not in all_issues:
                        all_issues.append(sent)
                    continue
                if self._sentence_has_keywords(sent, _DECISION_KW_RE):
                    if sent not in all_decisions:
                        all_decisions.append(sent)
                if self._sentence_has_keywords(sent, _ACTION_KW_RE):
                    person = ""
                    for pattern in _RE_PERSON_PATTERNS:
                        match = pattern.search(sent)
                        if match:
                            _PRONOUN_CHARS = set("我你他她它")
                            for g in match.groups():
                                if g and _RE_PERSON_CHECK.match(g) and not any(ch in _PRONOUN_CHARS for ch in g):
                                    person = g
                                    break
                            if person:
                                break
                    if not person:
                        pos_persons = self._extract_persons_by_pos(block)
                        if pos_persons:
                            person = pos_persons[0]
                    deadline = ""
                    for pattern in _RE_DEADLINE_PATTERNS:
                        match = pattern.search(sent)
                        if match:
                            deadline = match.group(0)
                            deadline = re.sub(r'^(截止|截止时间|截止日期|deadline)[：:]\s*', '', deadline)
                            break
                    cleaned = re.sub(r'^[，,。.！!？?\s]+', '', sent)
                    if cleaned and len(cleaned) > 5:
                        all_action_items.append({
                            "content": cleaned,
                            "responsible_person": person,
                            "deadline": deadline,
                            "priority": "medium",
                        })

            if self.jieba_loaded:
                import jieba.analyse
                tags = jieba.analyse.extract_tags(block, topK=3)
                if tags:
                    all_points.append("、".join(tags))

        seen_actions = set()
        unique_actions = []
        for item in all_action_items:
            key = (item["responsible_person"], item["content"][:30])
            if key not in seen_actions:
                seen_actions.add(key)
                unique_actions.append(item)

        seen_decisions = []
        for d in all_decisions:
            if d not in seen_decisions:
                seen_decisions.append(d)

        seen_issues = []
        for i in all_issues:
            if i not in seen_issues:
                seen_issues.append(i)

        decisions_str = "\n".join([f"• {d}" for d in seen_decisions]) if seen_decisions else "会议中未明确记录关键决策"
        issues_str = "\n".join([f"• {i}" for i in seen_issues]) if seen_issues else "无明确遗留问题记录"
        points_str = "\n".join([f"• {p}" for p in all_points[:8]]) if all_points else "详见会议原始记录"

        ai_participants = self.extract_participants(clean_text, _corrected=True)
        final_participants = ai_participants or participants

        result = {
            "topic": self.extract_topic(clean_text, title, _corrected=True),
            "participants": final_participants,
            "overview": self.extract_overview(clean_text, _corrected=True),
            "discussion_points": points_str,
            "key_decisions": decisions_str,
            "action_items": unique_actions,
            "unresolved_issues": issues_str,
            "summary": self.generate_summary(clean_text, decisions_str, unique_actions, issues_str, _corrected=True),
        }

        # 如果有模板结构，将模板信息添加到结果中
        if template_structure:
            result["template_structure"] = template_structure

        return result



import logging

def _mask_key(key: str) -> str:
    """
    安全显示 API Key

    对 API Key 进行脱敏处理，只显示前6位和后4位。
    用于日志记录，避免泄露敏感信息。

    Args:
        key (str): API Key

    Returns:
        str: 脱敏后的 API Key

    Example:
        >>> _mask_key("sk-1234567890abcdef")
        "sk-1234****cdef"
    """
    if not key or key == "your-deepseek-api-key":
        return "<NOT_CONFIGURED>"
    if len(key) < 12:
        return key[:4] + "****"
    return key[:6] + "****" + key[-4:]


# ==================== DeepSeek AI 处理器 ====================

# DeepSeek 系统提示词：定义 AI 的角色和输出格式
DEEPSEEK_SYSTEM_PROMPT = """你是专业的会议纪要分析师。严格从会议文本中提取信息，返回合法JSON。

## 输出格式（严格JSON，无任何额外文字）

{
  "topic": "一句话概括会议主题",
  "participants": "张三、李四、王五",
  "overview": "2-3句话概述会议核心内容和结论",
  "discussion_points": "• 第一个讨论要点\n• 第二个讨论要点\n• 第三个讨论要点",
  "key_decisions": "• 决策一：具体内容\n• 决策二：具体内容",
  "action_items": [
    {"content": "具体可执行的行动项", "responsible_person": "负责人", "deadline": "截止日期或时间", "priority": "high"}
  ],
  "unresolved_issues": "• 问题一\n• 问题二",
  "summary": "一段话总结本次会议的成果、待办和遗留问题"
}

## 字段规则
- topic: 从讨论内容提炼，不是文件名
- participants: 识别所有发言人（"张三说"→张三）和被提及的人名，用顿号分隔
- discussion_points: 每条一个要点句，用\\n• 分隔，至少3条
- key_decisions: 只提取明确做出的决定（含有"决定/确定/同意/通过/采用"等），没有则填"本次会议未做出明确决策"
- action_items: 必须是具体可执行的任务，包含负责人和deadline；从"需要做/安排/跟进/完成/提交"等关键词识别；没有则返回空数组[]
- unresolved_issues: 未达成共识或待后续确认的问题；没有则填"无遗留问题"
- summary: 一句话概括决策数、行动项数和遗留问题数

## 约束
1. 只返回JSON，不要```json```包裹，不要解释
2. 从原文提取，禁止编造不存在的内容
3. 所有字段必须有值，不允许null"""


# ==================== Qwen3 本地模型 Prompt ====================

# 简洁模式：适合短文本或快速处理
QWEN_SYSTEM_PROMPT_BRIEF = """从会议文本提取信息，输出JSON。简洁模式。

## 输出格式
{"topic":"主题","participants":"人员","overview":"概述","discussion_points":"• 要点1\n• 要点2","key_decisions":"• 决策1","action_items":[{"content":"任务","responsible_person":"负责人","deadline":"时间","priority":"high"}],"unresolved_issues":"• 问题1","summary":"总结"}

## 规则
- topic: 一句话概括
- participants: 顿号分隔所有人名
- overview: 1-2句话概括核心
- discussion_points: 每条以•开头，2-3条关键要点
- key_decisions: 只写明确决定，没有写"无决策"
- action_items: 只写确认要做的任务，空则[]
- unresolved_issues: 未解决的问题，没有写"无"
- summary: 一句话
- 只输出JSON，不要多余文字
- 从原文提取，不编造"""

# 标准模式：平衡详细度和处理速度
QWEN_SYSTEM_PROMPT_NORMAL = """从会议文本提取信息，输出JSON。标准模式。

## 输出格式
{"topic":"主题","participants":"人员","overview":"概述","discussion_points":"• 要点1\n• 要点2","key_decisions":"• 决策1","action_items":[{"content":"任务","responsible_person":"负责人","deadline":"时间","priority":"high"}],"unresolved_issues":"• 问题1","summary":"总结"}

## 规则
- topic: 一句话概括会议核心
- participants: 顿号分隔所有人名（发言人+被提及的人）
- overview: 3-4句话描述会议背景、讨论内容和结果
- discussion_points: 每条以•开头，换行分隔，至少3-5条详细要点
- key_decisions: 详细描述每个决策的背景和内容
- action_items: 包含任务描述、负责人、截止时间、优先级
- unresolved_issues: 描述问题的具体情况和影响
- summary: 2-3句话总结会议成果
- 只输出JSON，不要多余文字
- 从原文提取，不编造"""

# 详细模式：适合需要完整分析的场景
QWEN_SYSTEM_PROMPT_DETAILED = """从会议文本提取信息，输出JSON。详细模式。

## 输出格式
{"topic":"主题","participants":"人员","overview":"概述","discussion_points":"• 要点1\n• 要点2","key_decisions":"• 决策1","action_items":[{"content":"任务","responsible_person":"负责人","deadline":"时间","priority":"high"}],"unresolved_issues":"• 问题1","summary":"总结"}

## 规则
- topic: 一句话概括会议核心议题
- participants: 顿号分隔所有人名（发言人+被提及的人+部门）
- overview: 详细描述会议背景、目的、讨论过程和主要成果（4-6句话）
- discussion_points: 每条以•开头，换行分隔，至少5-8条详细要点，包含具体数据和细节
- key_decisions: 详细描述每个决策的背景、理由和具体内容
- action_items: 详细任务描述、负责人、截止时间、优先级、依赖关系
- unresolved_issues: 详细描述问题的具体情况、影响范围和建议解决方案
- summary: 详细总结会议成果、关键决策和下一步计划
- 只输出JSON，不要多余文字
- 从原文提取，不编造"""

# 默认使用标准模式
QWEN_SYSTEM_PROMPT = QWEN_SYSTEM_PROMPT_NORMAL




class DeepSeekNLPProcessor:
    """
    DeepSeek AI 驱动的 NLP 处理器

    使用 DeepSeek 云端 API 进行会议信息提取。
    优点：效果最好，理解能力强
    缺点：需要网络，有 API 费用

    使用示例：
        processor = DeepSeekNLPProcessor()
        result = processor.process("会议文本...")
    """

    def __init__(self):
        """
        初始化 DeepSeek 处理器

        从配置文件加载 API 密钥、基础 URL 和模型名称。
        """
        self.api_key = DEEPSEEK_API_KEY
        self.base_url = DEEPSEEK_BASE_URL
        self.model = DEEPSEEK_MODEL
        self._log_config()

    # ==================== 内部日志方法 ====================

    def _log_config(self):
        """启动时记录一次配置信息"""
        logger.info("=" * 50)
        logger.info("DeepSeekNLPProcessor 初始化")
        logger.info(f"  Base URL : {self.base_url}")
        logger.info(f"  Model    : {self.model}")
        logger.info(f"  API Key  : {_mask_key(self.api_key)}")
        if self.api_key == "your-deepseek-api-key":
            logger.warning("⚠  未设置 DEEPSEEK_API_KEY 环境变量！使用关键词匹配兜底")
            logger.warning("   设置方式：$env:DEEPSEEK_API_KEY = 'sk-你的key'")
        logger.info("=" * 50)

    def _log_request(self, text: str):
        """记录请求概览"""
        text_len = len(text)
        logger.info(f"📤 请求发送 → model={self.model}, 文本长度={text_len} 字符")
        logger.debug(f"   文本前 100 字符: {text[:100].strip()!r}")

    def _log_response_success(self, response):
        """记录成功响应"""
        try:
            usage = response.usage
            logger.info(f"✅ 响应成功 | tokens: 输入={usage.prompt_tokens}, "
                        f"输出={usage.completion_tokens}, "
                        f"总计={usage.total_tokens}")
        except Exception:
            logger.info("✅ 响应成功 (tokens 信息不可用)")

    # ==================== 主流程 ====================

    def process(self, text: str, title: str = "", participants: str = "", max_tokens: int = 0, template_structure: str = None) -> dict:
        """
        处理会议文本，提取结构化信息

        流程：
        1. 构造用户消息（包含模板提示）
        2. 调用 DeepSeek API
        3. 解析返回的 JSON
        4. 如果失败，降级到关键词匹配

        Args:
            text (str): 会议文本
            title (str): 会议标题（可选）
            participants (str): 参会人员（可选）
            max_tokens (int): 最大 token 数（未使用）
            template_structure (str): 模板结构（可选）

        Returns:
            dict: 结构化的会议信息
        """
        # 构造模板提示
        template_hint = ""
        if template_structure:
            template_hint = f"\n\n请按照以下会议结构模板提取信息：\n{template_structure}\n"

        user_message = f"请从以下会议文本中提取并总结会议信息，包括会议标题、参会人员等。{template_hint}\n\n会议文本：\n{text}"

        # 调用 DeepSeek API
        result = self._call_deepseek(user_message)

        # 降级处理
        if result is None:
            logger.warning("⚠  DeepSeek API 调用失败，降级到关键词匹配")
            fallback_result = _get_nlp_fallback().process(text, title, participants, template_structure=template_structure)
            logger.info("✅ 降级完成，使用关键词匹配结果")
            return fallback_result

        # 返回结构化结果
        logger.info("✅ DeepSeek 智能提取完成，返回结构化结果")
        return {
            "topic": result.get("topic", "会议记录"),
            "participants": result.get("participants", ""),
            "overview": result.get("overview", ""),
            "discussion_points": result.get("discussion_points", ""),
            "key_decisions": result.get("key_decisions", "会议中未明确记录关键决策"),
            "action_items": result.get("action_items", []),
            "unresolved_issues": result.get("unresolved_issues", "无明确遗留问题记录"),
            "summary": result.get("summary", ""),
        }

    # ==================== API 调用 ====================

    def _call_deepseek(self, user_message: str) -> Optional[dict]:
        """
        调用 DeepSeek API

        使用 OpenAI 兼容接口调用 DeepSeek 模型。

        Args:
            user_message (str): 用户消息

        Returns:
            dict: 解析后的 JSON 结果，失败返回 None
        """
        self._log_request(user_message)

        try:
            from openai import OpenAI

            # 创建 OpenAI 客户端
            client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )

            # 调用 API
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": DEEPSEEK_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.3,  # 低温度，输出更确定
                max_tokens=4096,
            )

            self._log_response_success(response)

            # 提取响应内容
            content = response.choices[0].message.content.strip()

            # 清理 markdown 代码块包裹
            if content.startswith("```"):
                lines = content.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                content = "\n".join(lines)

            # 解析 JSON
            return json.loads(content)

        except ImportError:
            logger.critical("openai 库未安装！请执行: pip install openai")
            return None

        except json.JSONDecodeError:
            logger.error(f"JSON 解析失败")
            logger.debug(f"原始返回片段: {content[:500]}")
            return None

        except Exception as e:
            self._log_api_error(e)
            return None

    def _log_api_error(self, error: Exception):
        """
        详细记录 API 错误信息

        根据错误类型提供具体的排查建议。

        Args:
            error (Exception): 异常对象
        """
        error_cls = type(error).__name__
        error_msg = str(error)

        logger.error(f"💥 API 调用异常 | 类型={error_cls}")

        # 细分常见错误并给出排查建议
        if "401" in error_msg or "authentication" in error_msg.lower() or "auth" in error_msg.lower():
            logger.error(f"  → 认证失败 (401)")
            logger.error(f"  → 当前 API Key: {_mask_key(self.api_key)}")
            logger.error(f"  → 请检查 DEEPSEEK_API_KEY 是否正确设置")
            logger.error(f"  → 设置方式: `$env:DEEPSEEK_API_KEY = 'sk-你的key'`")
            logger.error(f"  → 或修改 backend/config.py 中的 DEEPSEEK_API_KEY 值")

        elif "402" in error_msg:
            logger.error(f"  → 余额不足 (402)")
            logger.error(f"  → 请检查 DeepSeek 账户余额")

        elif "429" in error_msg or "rate" in error_msg.lower():
            logger.error(f"  → 请求频率限制 (429)")
            logger.error(f"  → 请稍后重试")

        elif "500" in error_msg or "502" in error_msg or "503" in error_msg:
            logger.error(f"  → DeepSeek 服务端错误 ({error_cls})")
            logger.error(f"  → 可能是临时故障，请稍后重试")

        elif "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
            logger.error(f"  → 请求超时")
            logger.error(f"  → 可能是网络问题或文本过长")

        elif "connection" in error_msg.lower():
            logger.error(f"  → 连接失败")
            logger.error(f"  → Base URL: {self.base_url}")
            logger.error(f"  → 请检查网络连接和 Base URL 是否正确")

        else:
            logger.error(f"  → 完整错误: {error_msg}")

        # 输出配置摘要辅助排查
        logger.debug(f"  → 配置摘要:")
        logger.debug(f"     Base URL : {self.base_url}")
        logger.debug(f"     Model    : {self.model}")
        logger.debug(f"     API Key  : {_mask_key(self.api_key)}")






# ==================== Qwen3 本地模型处理器 ====================

from config import LOCAL_MODEL_NAME, LOCAL_MODEL_CACHE, LOCAL_MODEL_DEVICE, LOCAL_MODEL_MAX_TOKENS, HF_ENDPOINT


class LocalQwenProcessor:
    """
    本地 Qwen3 模型处理器

    使用 HuggingFace transformers 加载 Qwen3 模型进行本地推理。
    优点：隐私安全，无需网络，无 API 费用
    缺点：需要 GPU（推荐），首次加载慢，需要下载模型

    支持的模型：
    - Qwen/Qwen2.5-0.6B-Instruct（默认，轻量级）
    - Qwen/Qwen2.5-1.5B-Instruct
    - Qwen/Qwen2.5-3B-Instruct
    - Qwen/Qwen2.5-7B-Instruct（需要大内存）

    使用示例：
        processor = LocalQwenProcessor()
        result = processor.process("会议文本...")
    """

    # 类级别共享变量（单例模式）
    _model = None      # 模型实例
    _tokenizer = None  # 分词器实例
    _load_time = 0.0   # 模型加载时间
    _use_onnx = False  # 是否使用 ONNX 加速

    def __init__(self):
        """
        初始化本地 Qwen3 处理器

        从配置文件加载模型名称、缓存目录、设备等配置。
        """
        self.model_name = LOCAL_MODEL_NAME
        self.cache_dir = LOCAL_MODEL_CACHE or None
        self.device = LOCAL_MODEL_DEVICE
        self._log_config()

    # ==================== 配置日志 ====================

    def _log_config(self):
        """记录配置信息"""
        logger.info("=" * 50)
        logger.info("LocalQwenProcessor 初始化")
        logger.info(f"  模型名称 : {self.model_name}")
        logger.info(f"  设备     : {self.device}")
        logger.info(f"  HF 镜像   : {HF_ENDPOINT}")
        logger.info("  缓存目录 : " + (self.cache_dir or "默认位置"))
        logger.info(f"  模型参数量: 0.6B（默认）/ 1.7B / 4B / 8B（需大内存）")
        logger.info("  模型文件约 1~2GB（0.6B），首次需下载")
        if self.device == "cpu":
            logger.info("  CPU 推理 0.6B 约 30~60 秒")
        logger.info("=" * 50)

    # ==================== 请求日志 ====================

    def _log_request(self, text: str, title: str = "", participants: str = ""):
        """记录请求详情"""
        text_len = len(text)
        logger.info("  | ========================================")
        logger.info("  | [请求详情] 本地 Qwen 推理请求")
        logger.info(f"  |   会议标题    : {title!r}" if title else "  |   会议标题    : (未提供)")
        logger.info(f"  |   参会人员    : {participants!r}" if participants else "  |   参会人员    : (未提供)")
        logger.info(f"  |   文本总长度  : {text_len} 字符 ({text_len//300} 约行)")
        logger.info(f"  |   文本前 200 字符:")
        for line in text[:200].strip().split("\n"):
            logger.info(f"  |     {line}")
        if text_len > 200:
            logger.info(f"  |     ... (剩余 {text_len - 200} 字符)")
            logger.info(f"  |   文本后 100 字符:")
            for line in text[-100:].strip().split("\n"):
                logger.info(f"  |     {line}")
        logger.info("  | ========================================")

    # ==================== 模型懒加载 ====================

    def _ensure_model(self):
        """
        确保模型已加载（懒加载 + 单例模式）

        首次调用时加载模型，后续调用复用已加载的模型。
        支持 GPU（4-bit 量化）和 CPU 两种模式。

        加载流程：
        1. 检查是否已加载
        2. 设置 CPU 线程数
        3. 加载 Tokenizer
        4. 加载模型（GPU 优先使用 4-bit 量化）
        5. 设置为评估模式

        Raises:
            ImportError: 缺少必要的 Python 包
            OSError: 模型下载或加载失败
        """
        if LocalQwenProcessor._model is not None:
            logger.debug("  模型已加载，复用缓存")
            return

        import os as _os
        import time as _time
        import os

        logger.info(f"  | 环境: HF_ENDPOINT={_os.environ.get('HF_ENDPOINT', '未设置')}")
        logger.info("  | ====== 模型加载开始 ======")
        t0 = _time.time()

        try:
            import sys
            # 优先使用已导入的模块
            if 'transformers' in sys.modules:
                AutoTokenizer = sys.modules['transformers'].AutoTokenizer
                AutoModelForCausalLM = sys.modules['transformers'].AutoModelForCausalLM
            else:
                from transformers import AutoTokenizer, AutoModelForCausalLM
            import torch

            # 设置 CPU 线程数
            import multiprocessing
            cpu_count = multiprocessing.cpu_count()
            optimal_threads = min(cpu_count, 8)
            torch.set_num_threads(optimal_threads)
            logger.info(f"  |   CPU 线程数: {optimal_threads} (共 {cpu_count} 核)")

            # 步骤 1: 加载 Tokenizer
            logger.info(f"  | 步骤 1/3: 加载 Tokenizer...")
            tokenizer = AutoTokenizer.from_pretrained(
                self.model_name,
                cache_dir=self.cache_dir,
                trust_remote_code=True,
            )
            logger.info(f"  |   Tokenizer OK, vocab_size={tokenizer.vocab_size}")

            # 步骤 2: 加载模型
            LocalQwenProcessor._use_onnx = False
            logger.info(f"  | 步骤 2/3: 使用 PyTorch 加载模型...")

            if self.device == "cuda":
                # GPU 模式：尝试 4-bit 量化
                try:
                    import bitsandbytes
                    from transformers import BitsAndBytesConfig
                    logger.info(f"  |   启用 4-bit 量化")
                    bnb_config = BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_compute_dtype=torch.float16,
                        bnb_4bit_use_double_quant=True,
                    )
                    model = AutoModelForCausalLM.from_pretrained(
                        self.model_name,
                        cache_dir=self.cache_dir,
                        trust_remote_code=True,
                        device_map="auto",
                        quantization_config=bnb_config,
                        low_cpu_mem_usage=True,
                    )
                    logger.info(f"  |   4-bit 量化加载成功")
                except Exception:
                    # 量化不可用，使用 float16
                    logger.info(f"  |   量化不可用，使用 float16 加载")
                    model = AutoModelForCausalLM.from_pretrained(
                        self.model_name,
                        cache_dir=self.cache_dir,
                        trust_remote_code=True,
                        torch_dtype=torch.float16,
                        device_map="auto",
                        low_cpu_mem_usage=True,
                    )
            else:
                # CPU 模式：使用 float32
                logger.info(f"  |   CPU 模式：直接加载 float32（0.6B 模型无需量化）")
                model = AutoModelForCausalLM.from_pretrained(
                    self.model_name,
                    cache_dir=self.cache_dir,
                    trust_remote_code=True,
                    torch_dtype=torch.float32,
                    low_cpu_mem_usage=True,
                )

            # 设置为评估模式
            model.eval()

            t1 = _time.time()
            load_secs = t1 - t0

            # 保存到类变量（单例模式）
            LocalQwenProcessor._tokenizer = tokenizer
            LocalQwenProcessor._model = model
            LocalQwenProcessor._load_time = load_secs

            logger.info(f"  | 步骤 3/3: 加载完成 (PyTorch)")
            logger.info(f"  |   设备: {model.device}")
            logger.info(f"  |   耗时: {load_secs:.1f}s")
            logger.info(f"  | ====== 模型加载结束 ======")

        except ImportError as e:
            logger.critical(f"  | ImportError: {e}")
            raise
        except OSError as e:
            err = str(e)
            logger.error(f"  | 模型下载/加载失败: {err[:200]}")
            if "Connection" in err or "connect" in err or "timeout" in err or "10060" in err:
                logger.error("  |   -> 无法连接 HuggingFace 服务器")
                logger.error("  |   -> 当前镜像: " + HF_ENDPOINT)
                logger.error("  |   -> 网络排查:")
                logger.error("  |      1. 测试镜像是否可达: curl " + HF_ENDPOINT)
                logger.error("  |      2. 尝试切换镜像: $env:HF_ENDPOINT='https://hf-mirror.com'")
                logger.error("  |      3. 或使用代理工具")
            elif "404" in err or "not found" in err:
                logger.error(f"  |   -> 模型 '{self.model_name}' 不存在，请检查名称")
            else:
                logger.error(f"  |   -> 未知文件错误: {err[:200]}")
            raise

    # ==================== 主流程 ====================

    def process(self, text: str, title: str = "", participants: str = "", max_tokens: int = 0, progress_callback=None) -> dict:
        """
        处理会议文本，提取结构化信息

        流程：
        1. 确保模型已加载
        2. 构造用户消息
        3. 调用 Qwen 推理
        4. 标准化返回结果
        5. 如果失败，降级到关键词匹配

        Args:
            text (str): 会议文本
            title (str): 会议标题（可选）
            participants (str): 参会人员（可选）
            max_tokens (int): 最大 token 数（控制输出详细度）
            progress_callback (callable): 进度回调函数（可选）

        Returns:
            dict: 结构化的会议信息
        """
        try:
            self._ensure_model()
        except ImportError:
            logger.warning("  | [降级] 缺少 Python 依赖包")
            logger.warning("  | [降级] 自动切换为关键词匹配")
            return _get_nlp_fallback().process(text, title, participants)
        except Exception as e:
            err = str(e)
            logger.error(f"  | [降级] 模型加载异常: {err[:150]}")
            logger.warning("  | [降级] 自动切换为关键词匹配")
            return _get_nlp_fallback().process(text, title, participants)

        user_message = f"请从以下会议文本中提取并总结会议信息，包括会议标题、参会人员等。\n\n会议文本：\n{text}"
        result = self._call_qwen(user_message, title, participants, max_tokens=max_tokens, progress_callback=progress_callback)

        if result is None:
            logger.warning("  | [降级] Qwen 推理失败，降级到关键词匹配")
            return _get_nlp_fallback().process(text, title, participants)

        # 类型标准化：key_decisions / unresolved_issues 可能是 list 或 string
        kd = result.get("key_decisions", [])
        if isinstance(kd, list):
            kd_str = "\n".join(kd) if kd else "会议中未明确记录关键决策"
        else:
            kd_str = kd if kd else "会议中未明确记录关键决策"

        ui = result.get("unresolved_issues", [])
        if isinstance(ui, list):
            ui_str = "\n".join(ui) if ui else "无明确遗留问题记录"
        else:
            ui_str = ui if ui else "无明确遗留问题记录"

        # discussion_points 也可能是 list
        dp = result.get("discussion_points", "")
        if isinstance(dp, list):
            dp_str = "\n".join(dp)
        else:
            dp_str = dp

        # 记录结果摘要
        logger.info(f"  | 最终结果结构")
        logger.info(f"  |   topic (主题)  : {result.get('topic', '')[:60]}")
        logger.info(f"  |   decisions     : {len(kd) if isinstance(kd, list) else len(kd_str.split(chr(10)))} 条")
        logger.info(f"  |   action_items  : {len(result.get('action_items', []))} 项")
        logger.info(f"  |   issues        : {len(ui) if isinstance(ui, list) else len(ui_str.split(chr(10)))} 条")
        logger.info("  | 本地 Qwen 提取完成，返回结构化结果")

        return {
            "topic": result.get("topic", "会议记录"),
            "participants": result.get("participants", ""),
            "overview": result.get("overview", ""),
            "discussion_points": dp_str,
            "key_decisions": kd_str,
            "action_items": result.get("action_items", []),
            "unresolved_issues": ui_str,
            "summary": result.get("summary", ""),
        }

    # ==================== Qwen 推理 ====================

    def _call_qwen(self, user_message: str, title: str = "", participants: str = "", max_tokens: int = 0, progress_callback=None) -> Optional[dict]:
        """
        调用 Qwen 模型进行推理

        使用流式输出，支持进度回调。
        推理流程：
        1. 根据 max_tokens 选择 prompt 模式
        2. 应用 chat template
        3. Tokenize 输入
        4. 流式生成
        5. 解析输出

        Args:
            user_message (str): 用户消息
            title (str): 会议标题
            participants (str): 参会人员
            max_tokens (int): 最大 token 数
            progress_callback (callable): 进度回调函数

        Returns:
            dict: 解析后的 JSON 结果，失败返回 None
        """
        import time as _time
        import threading

        self._log_request(user_message, title, participants)

        try:
            tokenizer = LocalQwenProcessor._tokenizer
            model = LocalQwenProcessor._model

            # 根据max_tokens选择合适的prompt
            actual_max = max_tokens if max_tokens > 0 else LOCAL_MODEL_MAX_TOKENS
            if actual_max <= 300:
                system_prompt = QWEN_SYSTEM_PROMPT_BRIEF
            elif actual_max <= 800:
                system_prompt = QWEN_SYSTEM_PROMPT_NORMAL
            else:
                system_prompt = QWEN_SYSTEM_PROMPT_DETAILED

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]
            prompt = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
            logger.info(f"  | [Prompt] 长度: {len(prompt)} 字符")

            # ── Tokenize ──
            t0 = _time.time()
            inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=32768)
            input_tokens = inputs["input_ids"].shape[1]
            logger.info(f"  |   tokens: {input_tokens}, 耗时: {(_time.time()-t0)*1000:.0f}ms")

            actual_max = max_tokens if max_tokens > 0 else LOCAL_MODEL_MAX_TOKENS

            # ── 推理（流式 + 真实 token 进度） ──
            gen_t0 = _time.time()

            import torch
            from transformers import TextIteratorStreamer

            streamer = TextIteratorStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)

            gen_kwargs = dict(
                **inputs,
                max_new_tokens=actual_max,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id,
                streamer=streamer,
            )

            def _generate():
                with torch.inference_mode():
                    model.generate(**gen_kwargs)

            gen_thread = threading.Thread(target=_generate, daemon=True)
            gen_thread.start()

            # prefill 阶段监控：第一个 token 到来前发 "处理输入中" 状态
            prefill_done = [False]
            def _prefill_monitor():
                while not prefill_done[0]:
                    _time.sleep(2)
                    if not prefill_done[0] and progress_callback:
                        try:
                            progress_callback(-1, 0, actual_max, "")
                        except Exception:
                            pass

            prefill_thread = threading.Thread(target=_prefill_monitor, daemon=True)
            prefill_thread.start()

            # 读取流式输出 — 每个 token 都是真实进度
            generated_text = ""
            token_count = 0

            for new_text in streamer:
                if not prefill_done[0]:
                    prefill_done[0] = True
                generated_text += new_text
                token_count += 1
                if progress_callback and token_count % 2 == 0:
                    progress = min(token_count / actual_max, 0.99)
                    try:
                        progress_callback(progress, token_count, actual_max, generated_text)
                    except Exception:
                        pass

            prefill_done[0] = True
            gen_thread.join()
            gen_t1 = _time.time()
            gen_secs = gen_t1 - gen_t0

            output_tokens = token_count
            tokens_per_sec = output_tokens / gen_secs if gen_secs > 0 else 0
            logger.info(f"  |   输入: {input_tokens} tokens, 输出: {output_tokens} tokens")
            logger.info(f"  |   耗时: {gen_secs:.1f}s, 速度: {tokens_per_sec:.1f} tokens/s")

            content = generated_text.strip()
            output_chars = len(content)
            logger.info(f"  |   解码字符数   : {output_chars}")
            logger.info(f"  |   压缩比       : {output_chars/output_tokens:.1f} 字符/token" if output_tokens > 0 else "  |   压缩比: N/A")

            # 去 <think>...</think> 思考过程（Qwen3 thinking 模型）
            original_content = content
            if "</think>" in content:
                think_end = content.rfind("</think>")
                content = content[think_end + len("</think>"):].strip()
                logger.info(f"  |   已剥离 <think> 思考过程（{think_end} 字符）")
            elif "<think>" in content and "</think>" not in content:
                logger.warning(f"  |   检测到未闭合的 <think> 标签，尝试提取...")
                think_start = content.find("<think>")
                content = content[think_start + len("<think>"):].strip()
                logger.info(f"  |   已剥离未闭合的 <think> 前缀")

            # 去 Markdown 代码块包裹
            if content.startswith("```"):
                lines = content.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                content = "\n".join(lines)
                if content != original_content:
                    logger.info(f"  |   已去除 Markdown 代码块包裹")

            # ── 原始输出全量日志 ──
            logger.info(f"  | ====== 模型原始输出 (完整) ======")
            for i, line in enumerate(content.split("\n")):
                logger.info(f"  |   [{i:03d}] {line}")
            logger.info(f"  | ====== 原始输出结束 ({output_chars} 字符) ======")

            # ── JSON 解析 ──
            logger.info(f"  | [JSON 解析] 开始解析模型输出...")

            # 清理JSON中的无效内容
            cleaned_content = content
            # 修复 participants 字段中的文件路径问题
            try:
                # 尝试直接解析
                result = json.loads(cleaned_content)
            except json.JSONDecodeError:
                # 如果失败，尝试清理后解析
                logger.warning(f"  | [JSON 解析] 直接解析失败，尝试清理...")
                # 移除可能的无效字符
                cleaned_content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', cleaned_content)
                # 修复 participants 字段中的路径问题
                cleaned_content = re.sub(
                    r'"participants":\s*"[^"]*[\\/][^"]*"',
                    '"participants": "参会人员"',
                    cleaned_content
                )
                result = json.loads(cleaned_content)

            logger.info(f"  | [JSON 解析] ✅ 解析成功，包含 {len(result)} 个字段")

            for key in result:
                val = result[key]
                if isinstance(val, str):
                    if len(val) > 80:
                        logger.info(f"  |   {key}: {val[:80]}... ({len(val)} 字符)")
                    else:
                        logger.info(f"  |   {key}: {val}")
                elif isinstance(val, list):
                    logger.info(f"  |   {key}: [{len(val)} 项]")
                    for i, item in enumerate(val):
                        if isinstance(item, dict):
                            content_val = item.get('content', item.get('task', ''))
                            person = item.get('responsible_person', item.get('person', '-'))
                            deadline = item.get('deadline', '-')
                            logger.info(f"  |     [{i}] {str(content_val)[:60]} | 负责人: {person} | 截止: {deadline}")
                        else:
                            logger.info(f"  |     [{i}] {str(item)[:80]}")
                else:
                    logger.info(f"  |   {key}: {val}")

            logger.info(f"  | [Qwen 推理] ✅ 完成")
            return result

        except json.JSONDecodeError:
            logger.error(f"  | [JSON 解析] ❌ 失败 - 模型返回非 JSON 格式")
            logger.error(f"  | ====== 原始返回 (完整) ======")
            try:
                for i, line in enumerate(content.split("\n")):
                    logger.error(f"  |   [{i:03d}] {line}")
            except Exception:
                pass
            logger.error(f"  | ====== 原始返回结束 ======")
            return None
        except Exception as e:
            self._log_error(e)
            return None

    def _log_error(self, error: Exception):
        """
        详细记录推理错误信息

        根据错误类型提供具体的排查建议。

        Args:
            error (Exception): 异常对象
        """
        import traceback
        error_msg = str(error)
        error_cls = type(error).__name__
        tb = traceback.format_exc()
        logger.error(f"  | ========================================")
        logger.error(f"  | [异常] Qwen 推理失败")
        logger.error(f"  | [异常] 类型       : {error_cls}")
        logger.error(f"  | [异常] 信息       : {error_msg[:500]}")
        if "out of memory" in error_msg.lower() or ("cuda" in error_msg.lower() and "memory" in error_msg.lower()):
            logger.error(f"  | [异常] 原因       : GPU 显存不足")
            logger.error(f"  | [异常] 解决方案:")
            logger.error(f"  |      1. 换更小的模型: $env:LOCAL_MODEL_NAME='Qwen/Qwen2.5-0.5B-Instruct'")
            logger.error(f"  |      2. 改用 CPU: $env:LOCAL_MODEL_DEVICE='cpu'")
            logger.error(f"  |      3. 安装 bitsandbytes 开启 4-bit: pip install bitsandbytes")
        elif "connect" in error_msg.lower() or "10060" in error_msg.lower():
            logger.error(f"  | [异常] 原因       : 网络连接失败")
            logger.error(f"  | [异常] 当前镜像   : {HF_ENDPOINT}")
            logger.error(f"  | [异常] 解决方案   : 切换镜像 $env:HF_ENDPOINT='https://hf-mirror.com'")
        elif "CUDA" in error_msg:
            logger.error(f"  | [异常] 原因       : CUDA 错误")
            logger.error(f"  | [异常] 解决方案   : $env:LOCAL_MODEL_DEVICE='cpu'")
        else:
            logger.error(f"  | [异常] 完整堆栈:")
            for line in tb.split("\n"):
                line = line.strip()
                if line:
                    logger.error(f"  |    {line}")
        # 内存快照
        try:
            import psutil
            mem = psutil.Process().memory_info()
            logger.error(f"  | [异常] 进程内存   : {mem.rss / 1024**3:.2f} GB")
            logger.error(f"  | [异常] 系统内存   : {psutil.virtual_memory().percent}% 已用")
        except Exception:
            pass
        logger.error(f"  | ========================================")

# ==================== 全局实例 ====================
# 创建三个处理器的全局实例，供外部调用
nlp_processor = NLPProcessor()  # 关键词匹配处理器（轻量级，无需外部 API）
deepseek_nlp_processor = DeepSeekNLPProcessor()  # DeepSeek AI 处理器（云端，效果最好）
local_qwen_processor = LocalQwenProcessor()  # 本地 Qwen3 处理器（本地推理，隐私安全）


def _get_nlp_fallback():
    """
    获取关键词匹配处理器单例

    供 AI 处理器降级时使用。

    Returns:
        NLPProcessor: 关键词匹配处理器实例
    """
    return nlp_processor

