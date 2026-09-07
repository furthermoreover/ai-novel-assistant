# -*- coding: utf-8 -*-
"""AI 小说创作助手 - 环境配置"""
import os
from dotenv import load_dotenv

load_dotenv()

# 数据库连接（用户本机 PostgreSQL 18.6, pgvector 已装）
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:YOUR_PASSWORD@localhost:29934/novel_assistant")

# 智谱 AI（embedding 用智谱，写作可自由切换厂商）
ZHIPU_API_KEY = os.getenv("ZHIPU_API_KEY", "")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "embedding-3")
EMBEDDING_DIM = 1024  # pgvector HNSW 索引上限 2000 维内
EMBEDDING_API_URL = "https://open.bigmodel.cn/api/paas/v4/embeddings"

# 写作/摘要接口（OpenAI 兼容格式，可切换厂商）：
#  智谱:  https://open.bigmodel.cn/api/paas/v4/chat/completions
#  阿里千问: https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
CHAT_API_URL = os.getenv("CHAT_API_URL", "https://open.bigmodel.cn/api/paas/v4/chat/completions")
# 写作接口的 API Key：填千问 Key 即用千问；留空则回退用智谱 Key
CHAT_API_KEY = os.getenv("CHAT_API_KEY", "") or ZHIPU_API_KEY
# 写作模型（OpenAI 兼容名）：
#  智谱: glm-4-flash(免费) / glm-4-air / glm-4-plus / glm-4.5
#  千问: qwen-turbo / qwen-plus / qwen-max
WRITING_MODEL = os.getenv("WRITING_MODEL", "glm-4-flash")
SUMMARIZE_MODEL = os.getenv("SUMMARIZE_MODEL", "glm-4-flash")

# 知识库目录
KNOWLEDGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "knowledge_base")

# 前端静态目录
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")

# 服务器
SERVER_HOST = os.getenv("SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))
