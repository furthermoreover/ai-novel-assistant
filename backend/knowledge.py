# -*- coding: utf-8 -*-
"""知识库：从 md 文件导入 + pgvector 语义检索"""
import os
import re
import uuid
from db import get_conn
from ai import embed_text
from config import KNOWLEDGE_DIR


def parse_markdown_chunks(content: str, topic: str, source: str):
    """按 ## 标题分块"""
    chunks = []
    parts = re.split(r"^## ", content, flags=re.MULTILINE)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        lines = part.split("\n")
        title = re.sub(r"^#+\s*", "", lines[0].strip())
        body = "\n".join(lines[1:]).strip()
        if title and len(body) >= 10:
            chunks.append({
                "topic": topic,
                "title": title[:255],
                "content": body,
                "tags": [],
                "source": source,
            })
    return chunks


def is_knowledge_empty() -> bool:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM knowledge_chunk")
            return cur.fetchone()["count"] == 0


def import_knowledge(overwrite: bool = False) -> dict:
    """扫描 knowledge_base/*.md 导入知识库"""
    if not os.path.exists(KNOWLEDGE_DIR):
        return {"imported": 0, "skipped": 0, "files": 0, "directory": KNOWLEDGE_DIR}

    files = sorted([f for f in os.listdir(KNOWLEDGE_DIR) if f.endswith(".md")])
    if not files:
        return {"imported": 0, "skipped": 0, "files": 0, "directory": KNOWLEDGE_DIR}

    with get_conn() as conn:
        with conn.cursor() as cur:
            if overwrite:
                cur.execute("DELETE FROM knowledge_chunk")

            imported = 0
            skipped = 0
            for fname in files:
                topic = re.sub(r"^\d+_", "", fname).replace(".md", "")
                with open(os.path.join(KNOWLEDGE_DIR, fname), "r", encoding="utf-8") as f:
                    content = f.read()
                chunks = parse_markdown_chunks(content, topic, fname)
                for ch in chunks:
                    if not overwrite:
                        cur.execute(
                            "SELECT id FROM knowledge_chunk WHERE topic=%s AND title=%s LIMIT 1",
                            (ch["topic"], ch["title"]),
                        )
                        if cur.fetchone():
                            skipped += 1
                            continue
                    try:
                        emb = embed_text(ch["content"])
                        cur.execute(
                            """INSERT INTO knowledge_chunk (id, topic, title, content, tags, source, embedding)
                               VALUES (%s, %s, %s, %s, %s, %s, %s::vector)""",
                            (str(uuid.uuid4()), ch["topic"], ch["title"], ch["content"],
                             ch["tags"], ch["source"], _vec_str(emb)),
                        )
                        imported += 1
                    except Exception:
                        # embedding 失败则跳过该块
                        skipped += 1
            conn.commit()

    return {"imported": imported, "skipped": skipped, "files": len(files), "directory": KNOWLEDGE_DIR}


def _vec_str(vec: list[float]) -> str:
    return "[" + ",".join(str(x) for x in vec) + "]"


def search_knowledge(query: str, limit: int = 4, topic: str | None = None) -> list[dict]:
    """语义检索：用 query 的 embedding 与库内向量算余弦距离"""
    try:
        emb = embed_text(query)
        vec = _vec_str(emb)
        sql = """
            SELECT id, topic, title, content, tags, source
            FROM knowledge_chunk
            WHERE embedding IS NOT NULL
              AND embedding <=> %s::vector < 0.6
        """
        params: list = [vec]
        if topic:
            sql += " AND topic = %s"
            params.append(topic)
        sql += " ORDER BY embedding <=> %s::vector LIMIT %s"
        params += [vec, limit]
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        return rows
    except Exception:
        return []


def list_topics() -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT topic, COUNT(*) AS count FROM knowledge_chunk GROUP BY topic ORDER BY topic")
            return cur.fetchall()


def list_by_topic(topic: str) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, topic, title, content, tags, source FROM knowledge_chunk WHERE topic=%s ORDER BY id",
                (topic,),
            )
            return cur.fetchall()
