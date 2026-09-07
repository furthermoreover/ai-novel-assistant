# -*- coding: utf-8 -*-
"""数据库连接与表结构"""
import psycopg
from psycopg.rows import dict_row
from config import DATABASE_URL

# 全局连接池（简单实现：每次请求新建连接，本地开发足够）
def get_conn():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)

# 表结构（与之前 Node 版保持一致，直接用已初始化的 novel_assistant 库）
# 表：novel_project, novel_outline, novel_character, novel_chapter, knowledge_chunk

def ensure_tables():
    """确保所有表存在（幂等）"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_chunk (
                  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                  topic VARCHAR(100) NOT NULL,
                  title VARCHAR(255) NOT NULL,
                  content TEXT NOT NULL,
                  tags TEXT[] DEFAULT '{}',
                  source VARCHAR(255),
                  embedding vector(1024),
                  _created_at TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  _updated_at TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_chunk_topic ON knowledge_chunk(topic);")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS novel_project (
                  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                  title VARCHAR(255) NOT NULL,
                  genre VARCHAR(100) DEFAULT '',
                  description TEXT DEFAULT '',
                  cover_image TEXT DEFAULT '',
                  _created_at TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  _updated_at TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS author_user (
                  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                  username VARCHAR(64) NOT NULL UNIQUE,
                  password_hash VARCHAR(512) NOT NULL,
                  _created_at TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """)
            # 项目归属作者（兼容已有数据：user_id 可空，首个注册用户自动接管）
            try:
                cur.execute("ALTER TABLE novel_project ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES author_user(id) ON DELETE SET NULL")
            except Exception:
                pass
            cur.execute("CREATE INDEX IF NOT EXISTS idx_novel_project_user ON novel_project(user_id);")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS novel_outline (
                  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                  project_id UUID NOT NULL REFERENCES novel_project(id) ON DELETE CASCADE,
                  main_storyline TEXT DEFAULT '',
                  world_setting TEXT DEFAULT '',
                  volume_plans TEXT DEFAULT '',
                  key_plot_points TEXT DEFAULT '',
                  foreshadowing TEXT DEFAULT '',
                  other_notes TEXT DEFAULT '',
                  _created_at TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  _updated_at TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_novel_outline_project_id ON novel_outline(project_id);")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS novel_character (
                  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                  project_id UUID NOT NULL REFERENCES novel_project(id) ON DELETE CASCADE,
                  name VARCHAR(255) NOT NULL,
                  age VARCHAR(50) DEFAULT '',
                  identity VARCHAR(255) DEFAULT '',
                  appearance TEXT DEFAULT '',
                  personality TEXT DEFAULT '',
                  background TEXT DEFAULT '',
                  motivation TEXT DEFAULT '',
                  relationships TEXT DEFAULT '',
                  speech_style TEXT DEFAULT '',
                  avatar TEXT DEFAULT '',
                  other_info TEXT DEFAULT '',
                  sort_order INTEGER DEFAULT 0,
                  _created_at TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  _updated_at TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_novel_character_project_id ON novel_character(project_id);")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS novel_chapter (
                  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                  project_id UUID NOT NULL REFERENCES novel_project(id) ON DELETE CASCADE,
                  chapter_number INTEGER NOT NULL DEFAULT 1,
                  title VARCHAR(255) NOT NULL,
                  content TEXT DEFAULT '',
                  summary TEXT DEFAULT '',
                  status VARCHAR(50) DEFAULT 'draft',
                  word_count INTEGER DEFAULT 0,
                  _created_at TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  _updated_at TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_novel_chapter_project_id ON novel_chapter(project_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_novel_chapter_number ON novel_chapter(project_id, chapter_number);")
            # 人物卡扩展：当前状态 + 最近出场章节（Agent 自主更新）
            try:
                cur.execute("ALTER TABLE novel_character ADD COLUMN IF NOT EXISTS current_status TEXT DEFAULT ''")
                cur.execute("ALTER TABLE novel_character ADD COLUMN IF NOT EXISTS last_appearance_chapter INTEGER DEFAULT NULL")
            except Exception:
                pass
            # 剧情时间线（Agent 分析章节后自动写入）
            cur.execute("""
                CREATE TABLE IF NOT EXISTS novel_timeline (
                  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                  project_id UUID NOT NULL REFERENCES novel_project(id) ON DELETE CASCADE,
                  chapter_number INTEGER NOT NULL,
                  location VARCHAR(255) DEFAULT '',
                  events TEXT DEFAULT '',
                  characters TEXT[] DEFAULT '{}',
                  _created_at TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_novel_timeline_project ON novel_timeline(project_id, chapter_number);")
            # 人物关系图（Agent 自动维护）
            cur.execute("""
                CREATE TABLE IF NOT EXISTS novel_relationship (
                  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                  project_id UUID NOT NULL REFERENCES novel_project(id) ON DELETE CASCADE,
                  char_a VARCHAR(255) NOT NULL,
                  char_b VARCHAR(255) NOT NULL,
                  relation VARCHAR(255) DEFAULT '',
                  sentiment VARCHAR(20) DEFAULT 'neutral',
                  trend VARCHAR(20) DEFAULT 'stable',
                  last_change_chapter INTEGER,
                  note TEXT DEFAULT '',
                  _created_at TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  _updated_at TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  UNIQUE (project_id, char_a, char_b)
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_novel_relationship_project ON novel_relationship(project_id);")
            # 伏笔库（Agent 自动埋收）
            cur.execute("""
                CREATE TABLE IF NOT EXISTS novel_foreshadowing (
                  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                  project_id UUID NOT NULL REFERENCES novel_project(id) ON DELETE CASCADE,
                  description TEXT NOT NULL,
                  type VARCHAR(50) DEFAULT 'other',
                  status VARCHAR(20) DEFAULT 'open',
                  planted_chapter INTEGER,
                  resolved_chapter INTEGER,
                  importance VARCHAR(20) DEFAULT 'medium',
                  _created_at TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_novel_foreshadowing_project ON novel_foreshadowing(project_id, status);")
            # 幂等创建 HNSW 索引（1024 维在限制内）
            try:
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_knowledge_chunk_embedding
                    ON knowledge_chunk USING hnsw (embedding vector_cosine_ops);
                """)
            except Exception:
                pass  # 已存在或版本不支持则忽略
        conn.commit()
