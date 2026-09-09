# AI 小说创作助手（AI Novel Assistant）

一个带 **RAG 知识库 + 自主剧情 Agent 长期记忆** 的本地网文创作工具。写小说时，AI 会记住你的大纲、人物、设定、伏笔和剧情时间线，自动注入精简状态包，防止剧情脱离设定。

> 完整功能需本地运行（Python 后端 + PostgreSQL + 你的 LLM API Key）。本仓库同时提供 GitHub Pages 静态展示页。

## ✨ 功能特性

- **📚 RAG 知识库**：内置 12 篇网文写作方法论（大纲/人物/情节/爽点/伏笔/玄幻专项等），向量化检索，写作时自动注入相关主题知识
- **🧠 自主剧情 Agent**：分析章节 → 自动更新人物卡（当前状态/动机）、世界设定、人物关系、伏笔库（埋/收）、剧情时间线
- **🧭 自动规划下一章**：基于完整记忆生成下一章大纲（自动生成对仗式章节名，如"剑冢将启"），可一键按规划新建章节
- **✍️ AI 写作**：10 个预设写作技能（黄金三章/打脸节奏/玄幻升级等），三种注入模式（自动/精简状态包/完整状态包）
- **💾 长期记忆**：所有设定存 PostgreSQL，重启不丢失；支持单章分析、全量同步（带进度条）
- **🔐 作者账号**：注册/登录，项目按账号隔离，首个注册账号自动接管本机已有项目
- **📖 章节管理**：导入已有小说（自动按"第X章"拆分）、阅读、摘要、续写

## 🧱 技术栈

- 后端：Python 3.10+ / FastAPI / psycopg3 / uvicorn
- 数据库：PostgreSQL 18 + pgvector（向量检索）
- 前端：原生 HTML/CSS/JS（无构建工具，单文件）
- LLM：智谱（embedding-3，知识库向量化）+ 千问 / 智谱（写作模型，可切换）
- 认证：PBKDF2 密码哈希 + HMAC 签名 Token（标准库实现，零第三方依赖）

## 📁 目录结构

```
├── backend/            # FastAPI 后端
│   ├── main.py         # 路由入口
│   ├── service.py      # 业务逻辑
│   ├── agent.py        # 自主剧情 Agent（分析/规划/状态包/全量同步）
│   ├── knowledge.py    # 知识库导入与向量检索
│   ├── auth.py         # 作者账号（注册/登录/Token）
│   ├── ai.py           # LLM 调用（embedding / chat）
│   ├── db.py           # 表结构与连接
│   └── config.py       # 配置读取（.env）
├── frontend/index.html # 前端单文件应用
├── knowledge_base/     # 网文写作方法论知识库（markdown 源文件）
├── prompts/            # Agent 提示词（章节分析 / 下一章规划）
├── docs/index.html     # GitHub Pages 静态展示页
└── start.bat           # Windows 一键启动
```

## 🚀 快速开始（本地运行）

### 前置要求

- Python 3.10+
- PostgreSQL 18（含 pgvector 扩展）
- 智谱 API Key（embedding）：https://open.bigmodel.cn
- 千问 API Key（写作，可选）：https://bailian.console.aliyun.com

### 步骤

```bash
# 1. 克隆仓库
git clone https://github.com/<your-name>/ai-novel-assistant.git
cd ai-novel-assistant

# 2. 创建数据库（本机 PostgreSQL，默认端口 5432）
#    psql -U postgres -c "CREATE DATABASE novel_assistant;"
#    psql -U postgres -d novel_assistant -c "CREATE EXTENSION IF NOT EXISTS vector;"

# 3. 配置 .env（复制模板并填入你的密钥）
cp .env.example .env

# 4. 创建虚拟环境并安装依赖
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt   # Windows
# 或 source .venv/bin/activate && pip install -r requirements.txt  # macOS/Linux

# 5. 启动
# Windows: 双击 start.bat（会自动检测端口、启动 PostgreSQL、拉起服务）
# 或手动：
#   .venv\Scripts\python -m uvicorn backend.main:app --port 8000
#   浏览器打开 http://127.0.0.1:8000
```

首次启动会自动导入 `knowledge_base/` 知识库并向量化（需智谱 Key）。

## 🎯 使用流程

1. **注册账号**（首个注册账号自动接管本机已有项目）
2. **新建小说** → 填书名/题材/简介
3. **导入或撰写章节** → 阅读章节时点「🧠 分析本章」更新记忆
4. **Agent 助手** → 查看记忆统计/关系图/时间线/伏笔库；点「规划下一章」生成大纲
5. **AI 写作** → 选择目标章节和技能，输入指令生成正文（自动注入记忆状态包）

## 📄 静态展示页

https://furthermoreover.github.io/ai-novel-assistant/

## 📝 License

[MIT](LICENSE)
