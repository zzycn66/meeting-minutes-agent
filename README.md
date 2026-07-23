# 会议纪要智能体 (Meeting Minutes Agent)

基于 AI 的智能会议纪要生成系统，支持会议录音上传、语音转写、NLP 智能分析，自动生成结构化会议纪要。

## 功能特性

- **语音转写** - 支持 MiMo ASR / Faster-Whisper 多种语音识别引擎
- **说话人分离** - 自动识别不同发言人，区分会议参与者
- **NLP 智能分析** - 基于 DeepSeek 大模型，自动提取关键信息
- **结构化纪要生成** - 自动生成包含议题、讨论、决议、待办事项的会议纪要
- **纪要导出** - 支持导出为 Word (.docx) 格式
- **会议问答** - 基于会议内容的智能问答功能
- **实时转写** - 支持 WebSocket 实时语音转写
- **用户管理** - 支持用户注册、登录、JWT 认证
- **纪要模板** - 支持自定义会议纪要模板

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI |
| 数据库 | SQLite + SQLAlchemy |
| 语音识别 | Faster-Whisper / MiMo ASR |
| 说话人分离 | Resemblyzer + 聚类算法 |
| NLP 大模型 | DeepSeek API / Qwen3 本地模型 |
| 前端 | HTML + CSS + JavaScript |
| 文档生成 | python-docx |

## 项目结构

```
会议纪要智能体/
├── main.py                 # 应用入口
├── config.py               # 配置文件
├── requirements.txt        # Python 依赖
├── .env                    # 环境变量 (不提交)
├── app/
│   ├── models.py           # 数据模型
│   ├── schemas.py          # Pydantic 数据结构
│   ├── database.py         # 数据库连接
│   ├── audio_processor.py  # 音频处理
│   ├── speaker_diarization.py  # 说话人分离
│   ├── qa_service.py       # 问答服务
│   ├── routes/             # API 路由
│   │   ├── auth.py         # 用户认证
│   │   ├── meetings.py     # 会议管理
│   │   ├── minutes.py      # 纪要管理
│   │   ├── export.py       # 导出功能
│   │   ├── audio.py        # 音频上传
│   │   ├── qa.py           # 问答接口
│   │   ├── templates.py    # 模板管理
│   │   ├── websocket.py    # WebSocket 实时转写
│   │   └── public.py       # 公共接口
│   ├── services/           # 业务服务
│   │   ├── meeting_service.py
│   │   ├── minutes_service.py
│   │   ├── nlp_service.py
│   │   ├── speech_service.py
│   │   └── streaming_service.py
│   └── utils/
│       └── regex_patterns.py
└── frontend/               # 前端静态文件
    ├── index.html
    ├── css/style.css
    └── js/app.js
```

## 环境要求

- Python 3.8+
- FFmpeg (音频处理依赖)

## 安装与运行

### 1. 克隆项目

```bash
git clone https://github.com/zzycn66/meeting-minutes-agent.git
cd meeting-minutes-agent
```

### 2. 创建虚拟环境

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 配置环境变量

创建 `.env` 文件：

```env
# DeepSeek API (必填)
DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

# MiMo ASR (可选，使用小米 MiMo 语音识别)
MIMO_API_KEY=your_mimo_api_key
MIMO_ASR_BASE_URL=https://api.xiaomimimo.com/v1

# Whisper 模型大小: tiny/base/small/medium/large-v3
WHISPER_MODEL_SIZE=medium

# 本地模型 (可选，使用 Qwen3 本地推理)
LOCAL_MODEL_NAME=Qwen/Qwen3-0.6B
LOCAL_MODEL_DEVICE=cpu

# HuggingFace 镜像 (国内用户)
HF_ENDPOINT=https://hf-mirror.com
```

### 5. 启动服务

```bash
python main.py
```

服务启动后访问：
- 前端页面: http://localhost:8000
- API 文档: http://localhost:8000/docs

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/auth/register` | POST | 用户注册 |
| `/api/auth/login` | POST | 用户登录 |
| `/api/meetings` | GET/POST | 会议列表/创建会议 |
| `/api/meetings/{id}` | GET/PUT/DELETE | 会议详情 |
| `/api/audio/upload` | POST | 上传音频文件 |
| `/api/minutes/generate/{meeting_id}` | POST | 生成会议纪要 |
| `/api/minutes/{id}` | GET/PUT | 纪要详情/编辑 |
| `/api/export/docx/{meeting_id}` | GET | 导出 Word 文档 |
| `/api/qa/ask` | POST | 会议问答 |
| `/ws/transcribe` | WebSocket | 实时语音转写 |

## 环境变量说明

| 变量名 | 必填 | 说明 |
|--------|------|------|
| `DEEPSEEK_API_KEY` | 是 | DeepSeek API 密钥 |
| `DEEPSEEK_BASE_URL` | 否 | DeepSeek API 地址，默认 https://api.deepseek.com |
| `DEEPSEEK_MODEL` | 否 | 模型名称，默认 deepseek-chat |
| `MIMO_API_KEY` | 否 | 小米 MiMo ASR API 密钥 |
| `WHISPER_MODEL_SIZE` | 否 | Whisper 模型大小，默认 medium |
| `LOCAL_MODEL_NAME` | 否 | 本地模型名称，默认 Qwen/Qwen3-0.6B |
| `LOCAL_MODEL_DEVICE` | 否 | 推理设备，默认 cpu |
| `HF_ENDPOINT` | 否 | HuggingFace 镜像地址 |

## License

MIT
