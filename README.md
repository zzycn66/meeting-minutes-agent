# 会议纪要智能体 (Meeting Minutes Agent)

基于 AI 的智能会议纪要生成系统，支持会议录音上传、语音转写、NLP 智能分析，自动生成结构化会议纪要。

## 功能特性

### 核心功能

- **语音转写** - 支持 Faster-Whisper / OpenAI Whisper / MiMo ASR 多种语音识别引擎，自动选择最优方案
- **说话人分离** - 基于 Resemblyzer 声纹特征 + 聚类算法，自动识别不同发言人
- **NLP 智能分析** - 三种处理方式可选：
  - 关键词规则匹配（jieba 分词，轻量级，无需外部 API）
  - DeepSeek AI 云端大模型（效果最佳）
  - Qwen3 本地大模型（隐私安全）
- **结构化纪要生成** - 自动生成包含议题、概述、讨论要点、关键决策、行动项、遗留问题的会议纪要
- **纪要导出** - 支持导出为 Word (.docx) 格式
- **会议问答** - 基于会议内容的智能问答，支持多轮对话
- **实时转写** - 支持 WebSocket 实时语音转写
- **会议模板** - 支持自定义会议纪要模板（周会/项目/评审/培训）
- **同音字纠错** - 自动修复语音转写中的常见错误
- **繁简转换** - 自动将繁体中文转换为简体中文
- **标点恢复** - 为无标点的转写文本自动恢复标点符号

### 用户系统

- 用户注册/登录
- JWT Token 认证
- 角色权限管理（admin/user）
- 会议记录归属管理

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        前端 (Frontend)                          │
│                  HTML + CSS + JavaScript                        │
│                  http://localhost:8000                          │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP / WebSocket
┌──────────────────────────▼──────────────────────────────────────┐
│                     FastAPI 应用服务                             │
│                     http://localhost:8000                       │
├─────────────────────────────────────────────────────────────────┤
│  路由层 (Routes)                                                │
│  ┌─────────┐ ┌──────────┐ ┌─────────┐ ┌──────────┐            │
│  │ 会议管理 │ │ 纪要管理  │ │ 用户认证 │ │ 音频上传 │            │
│  └─────────┘ └──────────┘ └─────────┘ └──────────┘            │
│  ┌─────────┐ ┌──────────┐ ┌─────────┐ ┌──────────┐            │
│  │ 导出功能 │ │ 模板管理  │ │ 问答接口 │ │ WebSocket│            │
│  └─────────┘ └──────────┘ └─────────┘ └──────────┘            │
├─────────────────────────────────────────────────────────────────┤
│  服务层 (Services)                                              │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐│
│  │ SpeechService    │  │ NLPService       │  │ QAService        ││
│  │ 语音识别服务      │  │ NLP信息提取       │  │ 会议问答(RAG)    ││
│  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘│
│           │                     │                     │          │
│  ┌────────▼─────────┐  ┌────────▼─────────┐  ┌────────▼─────────┐│
│  │ Faster-Whisper   │  │ DeepSeek API     │  │ Qwen3 本地模型   ││
│  │ OpenAI Whisper   │  │ (纪要生成)       │  │ (会议问答)       ││
│  │ MiMo ASR         │  │ jieba 关键词匹配 │  │ sentence-        ││
│  │ Resemblyzer      │  │                  │  │ transformers     ││
│  └──────────────────┘  └──────────────────┘  └──────────────────┘│
├─────────────────────────────────────────────────────────────────┤
│  数据层 (Data)                                                  │
│  ┌──────────────────┐  ┌──────────────────┐                    │
│  │ SQLite           │  │ 文件存储          │                    │
│  │ SQLAlchemy ORM   │  │ 音频文件          │                    │
│  └──────────────────┘  └──────────────────┘                    │
└─────────────────────────────────────────────────────────────────┘
```

## 技术栈

| 层级 | 技术 | 版本要求 | 说明 |
|------|------|----------|------|
| 后端框架 | FastAPI | >=0.68.0 | 异步 Web 框架 |
| ASGI 服务器 | Uvicorn | >=0.15.0 | 高性能 ASGI 服务器 |
| 数据库 | SQLite | - | 轻量级嵌入式数据库 |
| ORM | SQLAlchemy | >=1.4.0,<2.0.0 | Python SQL 工具包 |
| 语音识别 | Faster-Whisper | >=0.9.0 | CTranslate2 加速的 Whisper |
| 语音识别 | OpenAI Whisper | >=20230117 | OpenAI 官方 Whisper |
| 语音识别 | MiMo ASR | - | 小米 MiMo 云端 ASR |
| 说话人分离 | Resemblyzer | >=0.1.3 | 声纹特征提取 |
| 聚类算法 | scikit-learn | >=1.0.0 | 机器学习库 |
| NLP 分词 | jieba | >=0.42 | 中文分词引擎 |
| NLP 大模型 | DeepSeek API | - | 云端大语言模型 |
| NLP 本地模型 | Qwen3 | - | 本地大语言模型 |
| 文档生成 | python-docx | >=0.8.11 | Word 文档生成 |
| 数据验证 | Pydantic | >=1.8.0,<2.0.0 | 数据校验 |
| 音频处理 | pydub | >=0.25.1 | 音频格式转换 |
| 音频降噪 | noisereduce | >=2.0.0 | 音频降噪 |
| 繁简转换 | zhconv | >=1.4.3 | 中文繁简转换 |
| 前端 | HTML/CSS/JS | - | 原生前端 |

## 项目结构

```
会议纪要智能体/
├── main.py                     # 应用入口，FastAPI 初始化
├── config.py                   # 配置文件，环境变量加载
├── requirements.txt            # Python 依赖清单
├── .env                        # 环境变量配置 (不提交到 Git)
│
├── app/                        # 后端应用代码
│   ├── __init__.py
│   ├── models.py               # SQLAlchemy 数据模型
│   │   ├── Meeting             # 会议记录表
│   │   ├── MeetingMinutes      # 会议纪要表
│   │   ├── ActionItem          # 行动项表
│   │   ├── User                # 用户表
│   │   ├── MeetingTemplate     # 会议模板表
│   │   └── QAHistory           # 问答历史表
│   │
│   ├── schemas.py              # Pydantic 请求/响应数据结构
│   ├── database.py             # 数据库连接配置
│   │
│   ├── audio_processor.py      # 音频预处理（降噪、格式转换）
│   ├── speaker_diarization.py  # 说话人分离（声纹特征 + 聚类）
│   ├── qa_service.py           # 会议问答服务
│   │
│   ├── routes/                 # API 路由层
│   │   ├── auth.py             # 用户认证 (注册/登录/JWT)
│   │   ├── meetings.py         # 会议管理 CRUD
│   │   ├── minutes.py          # 纪要管理
│   │   ├── export.py           # 纪要导出 (Word)
│   │   ├── audio.py            # 音频上传/识别
│   │   ├── qa.py               # 会议问答
│   │   ├── templates.py        # 会议模板管理
│   │   ├── websocket.py        # WebSocket 实时转写
│   │   └── public.py           # 公共接口
│   │
│   ├── services/               # 业务逻辑层
│   │   ├── meeting_service.py  # 会议业务逻辑
│   │   ├── minutes_service.py  # 纪要生成逻辑
│   │   ├── nlp_service.py      # NLP 信息提取
│   │   ├── speech_service.py   # 语音识别服务
│   │   └── streaming_service.py # 流式处理服务
│   │
│   └── utils/
│       └── regex_patterns.py   # 正则表达式模式库
│
└── frontend/                   # 前端静态文件
    ├── index.html              # 主页面
    ├── css/style.css           # 样式文件
    └── js/app.js               # 前端逻辑
```

## 环境要求

- **Python**: 3.8+
- **FFmpeg**: 音频格式转换依赖（[安装指南](https://ffmpeg.org/download.html)）
- **操作系统**: Windows / macOS / Linux
- **内存**: 建议 4GB+（使用本地模型时建议 8GB+）

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

# macOS / Linux
source venv/bin/activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 安装 FFmpeg

**Windows:**
```bash
# 使用 winget
winget install FFmpeg

# 或使用 choco
choco install ffmpeg

# 或从官网下载: https://ffmpeg.org/download.html
```

**macOS:**
```bash
brew install ffmpeg
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt update && sudo apt install ffmpeg
```

### 5. 配置环境变量

在项目根目录创建 `.env` 文件：

```env
# ==================== 必填配置 ====================

# DeepSeek API 密钥 (用于 NLP 信息提取)
DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

# ==================== 可选配置 ====================

# MiMo ASR (小米云端语音识别，可选)
MIMO_API_KEY=your_mimo_api_key
MIMO_ASR_BASE_URL=https://api.xiaomimimo.com/v1

# Whisper 模型配置
# 可选值: tiny / base / small / medium / large-v3
# tiny:  最快，准确率最低
# small: 速度与准确率平衡
# medium: 推荐大多数用户使用 (默认)
# large-v3: 最准，但需要更多资源
WHISPER_MODEL_SIZE=medium

# 本地大模型配置 (可选，使用 Qwen3 本地推理)
LOCAL_MODEL_NAME=Qwen/Qwen3-0.6B
LOCAL_MODEL_DEVICE=cpu
LOCAL_MODEL_MAX_TOKENS=1024

# HuggingFace 镜像 (国内用户推荐)
HF_ENDPOINT=https://hf-mirror.com

# CORS 配置
ALLOWED_ORIGINS=http://localhost:8000
```

### 6. 启动服务

```bash
python main.py
```

启动成功后访问：
- **前端页面**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs (Swagger UI)
- **ReDoc 文档**: http://localhost:8000/redoc

## API 接口文档

### 用户认证

| 接口 | 方法 | 说明 | 认证 |
|------|------|------|------|
| `/api/auth/register` | POST | 用户注册 | 否 |
| `/api/auth/login` | POST | 用户登录 | 否 |

### 会议管理

| 接口 | 方法 | 说明 | 认证 |
|------|------|------|------|
| `/api/meetings` | GET | 获取会议列表 | 是 |
| `/api/meetings` | POST | 创建会议 | 是 |
| `/api/meetings/{id}` | GET | 获取会议详情 | 是 |
| `/api/meetings/{id}` | PUT | 更新会议 | 是 |
| `/api/meetings/{id}` | DELETE | 删除会议 | 是 |

### 音频处理

| 接口 | 方法 | 说明 | 认证 |
|------|------|------|------|
| `/api/audio/upload` | POST | 上传音频文件 | 是 |
| `/api/audio/transcribe` | POST | 音频转写 | 是 |
| `/ws/transcribe` | WebSocket | 实时语音转写 | 否 |

### 纪要管理

| 接口 | 方法 | 说明 | 认证 |
|------|------|------|------|
| `/api/minutes/generate/{meeting_id}` | POST | 生成会议纪要 | 是 |
| `/api/minutes/{id}` | GET | 获取纪要详情 | 是 |
| `/api/minutes/{id}` | PUT | 编辑纪要 | 是 |
| `/api/export/docx/{meeting_id}` | GET | 导出 Word 文档 | 是 |

### 问答功能

| 接口 | 方法 | 说明 | 认证 |
|------|------|------|------|
| `/api/qa/ask` | POST | 会议问答 | 是 |

### 模板管理

| 接口 | 方法 | 说明 | 认证 |
|------|------|------|------|
| `/api/templates` | GET | 获取模板列表 | 是 |
| `/api/templates` | POST | 创建模板 | 是 |

### 公共接口

| 接口 | 方法 | 说明 | 认证 |
|------|------|------|------|
| `/health` | GET | 健康检查 | 否 |
| `/` | GET | 前端页面 | 否 |

## 使用教程

### 第一步：启动服务

```bash
# 激活虚拟环境
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

# 启动服务
python main.py
```

启动成功后，终端会显示：
```
==================================================
  会议纪要智能体 (Meeting Minutes Agent)
  API服务已启动: http://localhost:8000
  API文档: http://localhost:8000/docs
==================================================
```

在浏览器中打开 **http://localhost:8000** 即可使用。

---

### 第二步：注册与登录

1. 打开浏览器访问 http://localhost:8000
2. 点击页面右上角的 **"登录"** 按钮
3. 在弹出的登录框中，点击 **"没有账号？立即注册"**
4. 填写注册信息：
   - **用户名**: 输入一个唯一的用户名（如 `zhangsan`）
   - **密码**: 设置密码（至少6位）
   - **显示名称**: 输入你的姓名（如 `张三`，选填）
5. 点击 **"注册"** 按钮完成注册
6. 注册成功后自动跳转到登录页，输入用户名和密码登录

> 登录后，页面右上角会显示你的用户名，表示已成功登录。

---

### 第三步：创建会议记录

登录后，你可以通过两种方式创建会议：

#### 方式一：上传音频文件

1. 在主页面找到 **"会议信息"** 卡片
2. 填写以下信息：
   - **会议标题**: 例如 `2024 产品规划讨论会`（可选，系统会根据内容自动生成）
   - **会议日期**: 选择会议日期（默认为当天）
   - **参会人员**: 输入参会人姓名，用顿号分隔，如 `张三、李四、王五`
3. 在 **"会议内容"** 区域，选择 **"音频上传"** 标签
4. 点击 **"选择文件"** 或 **拖拽音频文件** 到上传区域
5. 支持的音频格式：`MP3`、`WAV`、`M4A`、`AAC`、`WMA`、`OGG`、`FLAC`、`WebM`
6. 文件大小限制：**100MB**
7. （可选）选择语音识别引擎：
   - **自动选择**（推荐）: 系统自动选择最优引擎
   - **Whisper**: 使用本地 Faster-Whisper 引擎
   - **MiMo**: 使用小米 MiMo 云端 ASR（需配置 API Key）
8. 点击 **"上传并识别"** 按钮，等待语音转写完成

#### 方式二：粘贴文本

1. 在 **"会议内容"** 区域，选择 **"文本输入"** 标签
2. 在文本框中粘贴会议文字记录
3. 点击 **"提交"** 按钮

> **提示**: 如果你已有会议的文字稿（如录音转写结果、会议笔记），可以直接粘贴，跳过语音识别步骤。

---

### 第四步：查看转写结果

音频上传并识别完成后：

1. 系统会自动显示 **转写结果**
2. 转写结果包含：
   - **识别引擎**: 显示使用的引擎（如 `faster-whisper`）
   - **处理耗时**: 显示识别用时（如 `3.2s`）
   - **说话人标签**: 自动识别的发言人（如 `【说话人1】`、`【说话人2】`）
3. 你可以 **编辑** 转写结果，修正识别错误
4. 确认无误后，点击 **"生成纪要"** 按钮

> **说话人分离**: 系统会自动识别音频中的不同发言人，并在文本中标注 `【说话人1】`、`【说话人2】` 等标签。你可以根据实际参会人员，在转写结果中手动修改为真实姓名。

---

### 第五步：生成会议纪要

点击 **"生成纪要"** 按钮后，系统会自动分析会议内容并生成结构化纪要。

生成的纪要包含以下部分：

| 部分 | 说明 |
|------|------|
| **会议主题** | 根据内容自动生成的会议主题 |
| **会议概述** | 会议内容的简要概述 |
| **讨论要点** | 会议中讨论的主要话题和观点 |
| **关键决策** | 会议中做出的重要决定 |
| **行动项** | 需要后续执行的任务，包含负责人和截止时间 |
| **遗留问题** | 未解决、待讨论的问题 |

生成完成后，你可以在页面上直接 **编辑** 各部分内容：
- 点击内容区域即可进入编辑模式
- 修改完成后点击 **"保存"** 按钮

---

### 第六步：导出 Word 文档

纪要生成并确认无误后：

1. 点击 **"导出 Word"** 按钮
2. 系统会自动生成 `.docx` 格式的会议纪要文件
3. 浏览器会自动下载该文件

导出的 Word 文档包含：
- 完整的会议信息（标题、日期、参会人员）
- 结构化的纪要内容（Markdown 格式转换为 Word 格式）
- 行动项列表（含负责人、截止时间、优先级）

---

### 第七步：会议问答（可选）

生成纪要后，你可以基于会议内容进行智能问答：

1. 在页面底部找到 **"会议问答"** 区域
2. 在输入框中输入你的问题，例如：
   - "这次会议讨论了哪些议题？"
   - "张三负责什么任务？"
   - "会议中有哪些遗留问题？"
3. 点击 **"提问"** 按钮
4. 系统会基于会议内容生成回答

> **提示**: 问答功能基于 Qwen3 本地大模型（RAG 架构），通过语义检索找到相关段落，再由 Qwen3 生成自然语言回答。无需联网，数据安全。

---

### 使用流程总结

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  注册/登录   │────▶│  创建会议    │────▶│  上传音频    │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                               │
                                               ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  导出 Word  │◀────│  生成纪要    │◀────│  语音转写    │
└─────────────┘     └──────┬──────┘     └─────────────┘
                           │
                           ▼
                     ┌─────────────┐
                     │  会议问答    │
                     └─────────────┘
```

---

### 高级功能

#### 使用会议模板

1. 点击会议信息卡片中的 **"选择模板"** 按钮
2. 从模板列表中选择合适的模板类型：
   - **周会模板**: 适合团队周会
   - **项目评审模板**: 适合项目阶段性评审
   - **需求评审模板**: 适合产品需求讨论
   - **培训模板**: 适合内部培训会议
3. 选择模板后，纪要会按照模板结构生成

#### 实时语音转写

1. 在页面中找到 **"实时转写"** 功能
2. 点击 **"开始录音"** 按钮
3. 系统会通过 WebSocket 实时将语音转换为文字
4. 点击 **"停止录音"** 结束转写
5. 转写结果会自动填充到会议内容区域

> **注意**: 实时转写功能需要浏览器支持 WebRTC，推荐使用 Chrome 或 Edge 浏览器。

#### 管理历史会议

1. 点击页面左上角的 **"刷新列表"** 按钮
2. 在左侧边栏查看所有历史会议记录
3. 点击任意会议记录可查看详情
4. 可对会议记录进行编辑、删除操作

## 环境变量说明

| 变量名 | 必填 | 默认值 | 说明 |
|--------|------|--------|------|
| `DEEPSEEK_API_KEY` | 是 | - | DeepSeek API 密钥 |
| `DEEPSEEK_BASE_URL` | 否 | `https://api.deepseek.com` | DeepSeek API 地址 |
| `DEEPSEEK_MODEL` | 否 | `deepseek-chat` | DeepSeek 模型名称 |
| `MIMO_API_KEY` | 否 | - | 小米 MiMo ASR API 密钥 |
| `MIMO_ASR_BASE_URL` | 否 | `https://api.xiaomimimo.com/v1` | MiMo ASR API 地址 |
| `WHISPER_MODEL_SIZE` | 否 | `medium` | Whisper 模型大小 |
| `LOCAL_MODEL_NAME` | 否 | `Qwen/Qwen3-0.6B` | 本地模型名称 |
| `LOCAL_MODEL_DEVICE` | 否 | `cpu` | 推理设备 (cpu/cuda) |
| `LOCAL_MODEL_MAX_TOKENS` | 否 | `1024` | 最大生成 token 数 |
| `HF_ENDPOINT` | 否 | `https://hf-mirror.com` | HuggingFace 镜像地址 |
| `ALLOWED_ORIGINS` | 否 | `http://localhost:8000` | CORS 允许的源 |

## 常见问题

### Q: Whisper 模型下载很慢？

设置 HuggingFace 镜像：
```env
HF_ENDPOINT=https://hf-mirror.com
```

### Q: 没有 GPU 能用吗？

可以。默认使用 CPU 推理，速度较慢但可用。如需 GPU 加速：
1. 安装 CUDA 版 PyTorch
2. 设置 `LOCAL_MODEL_DEVICE=cuda`

### Q: 音频格式不支持？

确保已安装 FFmpeg，系统会自动进行格式转换。支持的格式：MP3, WAV, M4A, AAC, WMA, OGG, FLAC, WebM。

### Q: 如何使用 MiMo ASR？

1. 申请小米 MiMo API Key
2. 在 `.env` 中配置 `MIMO_API_KEY`
3. 上传音频时选择 MiMo 引擎

### Q: 如何部署到生产环境？

推荐使用 Docker 或 Gunicorn：
```bash
# 使用 uvicorn 启动
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4

# 或使用 Docker
docker run -p 8000:8000 -e DEEPSEEK_API_KEY=xxx meeting-minutes-agent
```

## License

MIT
