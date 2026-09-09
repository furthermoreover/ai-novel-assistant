# -*- coding: utf-8 -*-
"""FastAPI 主入口：AI 小说创作助手"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from config import FRONTEND_DIR, SERVER_HOST, SERVER_PORT
from db import ensure_tables, get_conn
from knowledge import import_knowledge, is_knowledge_empty, search_knowledge, list_topics, list_by_topic
import service
import agent
import auth

app = FastAPI(title="AI 小说创作助手")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- 请求模型 ----------
class ProjectCreate(BaseModel):
    title: str
    genre: str = ""
    description: str = ""

class ProjectUpdate(BaseModel):
    title: str | None = None
    genre: str | None = None
    description: str | None = None
    cover_image: str | None = None

class OutlineUpdate(BaseModel):
    main_storyline: str | None = None
    world_setting: str | None = None
    volume_plans: str | None = None
    key_plot_points: str | None = None
    foreshadowing: str | None = None
    other_notes: str | None = None

class CharacterCreate(BaseModel):
    name: str
    age: str | None = None
    identity: str | None = None
    appearance: str | None = None
    personality: str | None = None
    background: str | None = None
    motivation: str | None = None
    relationships: str | None = None
    speech_style: str | None = None
    avatar: str | None = None
    other_info: str | None = None
    sort_order: int = 0

class CharacterUpdate(BaseModel):
    name: str | None = None
    age: str | None = None
    identity: str | None = None
    appearance: str | None = None
    personality: str | None = None
    background: str | None = None
    motivation: str | None = None
    relationships: str | None = None
    speech_style: str | None = None
    avatar: str | None = None
    other_info: str | None = None
    sort_order: int | None = None

class ChapterCreate(BaseModel):
    title: str
    content: str = ""
    chapter_number: int | None = None

class ChapterUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    summary: str | None = None
    status: str | None = None

class GenerateRequest(BaseModel):
    writing_instruction: str
    skill_id: str | None = None
    skill_mode: str = "standard"
    selected_topic: str | None = None

class ImportRequest(BaseModel):
    overwrite: bool = False

class RegisterRequest(BaseModel):
    username: str
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str


# ---------- 认证 ----------
def get_current_user(authorization: str | None = Header(None)) -> dict:
    """从 Authorization: Bearer <token> 解析当前用户"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "请先登录")
    user = auth.verify_token(authorization[7:].strip())
    if not user:
        raise HTTPException(401, "登录已过期，请重新登录")
    return user


def guard_project(pid: str, user: dict) -> dict:
    """校验项目归属，返回项目；不属于当前用户一律 404（不泄露存在性）"""
    p = service.get_project(pid)
    if not p or p.get("user_id") != user["id"]:
        raise HTTPException(404, "项目不存在")
    return p


@app.post("/api/auth/register")
def api_register(body: RegisterRequest):
    try:
        user = auth.register(body.username, body.password)
        token = auth.create_token(user["id"])
        return {"token": token, "user": user}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/auth/login")
def api_login(body: LoginRequest):
    try:
        user = auth.login(body.username, body.password)
        token = auth.create_token(user["id"])
        return {"token": token, "user": user}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/auth/me")
def api_me(user: dict = Depends(get_current_user)):
    return user


# ---------- 知识库 ----------
@app.get("/api/knowledge/topics")
def api_topics():
    return list_topics()

@app.get("/api/knowledge/topic/{topic}")
def api_topic(topic: str):
    return list_by_topic(topic)

@app.post("/api/knowledge/search")
def api_search(body: dict):
    q = (body or {}).get("query", "")
    return search_knowledge(q, 4)

@app.post("/api/knowledge/import")
def api_import(body: ImportRequest | None = None):
    overwrite = body.overwrite if body else False
    return import_knowledge(overwrite)

# ---------- 项目 ----------
@app.get("/api/projects")
def api_projects(user: dict = Depends(get_current_user)):
    return service.list_projects(user["id"])

@app.post("/api/projects")
def api_create_project(body: ProjectCreate, user: dict = Depends(get_current_user)):
    return service.create_project(body.title, body.genre, body.description, user_id=user["id"])

@app.get("/api/projects/{pid}")
def api_project(pid: str, user: dict = Depends(get_current_user)):
    return guard_project(pid, user)

@app.patch("/api/projects/{pid}")
def api_update_project(pid: str, body: ProjectUpdate, user: dict = Depends(get_current_user)):
    guard_project(pid, user)
    p = service.update_project(pid, **body.model_dump(exclude_none=True))
    if not p:
        raise HTTPException(404, "项目不存在")
    return p

@app.delete("/api/projects/{pid}")
def api_delete_project(pid: str, user: dict = Depends(get_current_user)):
    guard_project(pid, user)
    service.delete_project(pid)
    return {"ok": True}

# ---------- 大纲 ----------
@app.get("/api/projects/{pid}/outline")
def api_outline(pid: str, user: dict = Depends(get_current_user)):
    guard_project(pid, user)
    o = service.get_outline(pid)
    if not o:
        raise HTTPException(404, "大纲不存在")
    return o

@app.patch("/api/projects/{pid}/outline")
def api_upsert_outline(pid: str, body: OutlineUpdate, user: dict = Depends(get_current_user)):
    guard_project(pid, user)
    return service.upsert_outline(pid, **body.model_dump(exclude_none=True))

# ---------- 人物 ----------
@app.get("/api/projects/{pid}/characters")
def api_characters(pid: str, user: dict = Depends(get_current_user)):
    guard_project(pid, user)
    return service.list_characters(pid)

@app.post("/api/projects/{pid}/characters")
def api_create_character(pid: str, body: CharacterCreate, user: dict = Depends(get_current_user)):
    guard_project(pid, user)
    return service.create_character(pid, body.name, **body.model_dump(exclude_none=True, exclude={"name"}))

@app.patch("/api/projects/{pid}/characters/{cid}")
def api_update_character(pid: str, cid: str, body: CharacterUpdate, user: dict = Depends(get_current_user)):
    guard_project(pid, user)
    c = service.update_character(pid, cid, **body.model_dump(exclude_none=True))
    if not c:
        raise HTTPException(404, "人物卡不存在")
    return c

@app.delete("/api/projects/{pid}/characters/{cid}")
def api_delete_character(pid: str, cid: str, user: dict = Depends(get_current_user)):
    guard_project(pid, user)
    service.delete_character(pid, cid)
    return {"ok": True}

# ---------- 章节 ----------
@app.get("/api/projects/{pid}/chapters")
def api_chapters(pid: str, user: dict = Depends(get_current_user)):
    guard_project(pid, user)
    return service.list_chapters(pid)

@app.post("/api/projects/{pid}/chapters")
def api_create_chapter(pid: str, body: ChapterCreate, user: dict = Depends(get_current_user)):
    guard_project(pid, user)
    return service.create_chapter(pid, body.title, body.content, body.chapter_number)

@app.post("/api/projects/{pid}/chapters/import")
def api_import_chapters(pid: str, body: dict, user: dict = Depends(get_current_user)):
    """导入已有小说文本（自动按『第X章』拆分）"""
    guard_project(pid, user)
    content = (body or {}).get("content", "")
    return service.import_chapters(pid, content)

@app.get("/api/projects/{pid}/chapters/{cid}")
def api_chapter(pid: str, cid: str, user: dict = Depends(get_current_user)):
    guard_project(pid, user)
    c = service.get_chapter(pid, cid)
    if not c:
        raise HTTPException(404, "章节不存在")
    return c

@app.patch("/api/projects/{pid}/chapters/{cid}")
def api_update_chapter(pid: str, cid: str, body: ChapterUpdate, user: dict = Depends(get_current_user)):
    guard_project(pid, user)
    c = service.update_chapter(pid, cid, **body.model_dump(exclude_none=True))
    if not c:
        raise HTTPException(404, "章节不存在")
    return c

@app.delete("/api/projects/{pid}/chapters/{cid}")
def api_delete_chapter(pid: str, cid: str, user: dict = Depends(get_current_user)):
    guard_project(pid, user)
    service.delete_chapter(pid, cid)
    return {"ok": True}

# ---------- AI ----------
@app.post("/api/projects/{pid}/chapters/{cid}/generate")
def api_generate(pid: str, cid: str, body: GenerateRequest, user: dict = Depends(get_current_user)):
    guard_project(pid, user)
    try:
        # Agent 状态包注入：skill-only 不注入；standard 精简层；deep 完整层
        if body.skill_mode == "skill-only":
            state_context = None
        else:
            state_context = agent.story_state_text(pid, mode="deep" if body.skill_mode == "deep" else "standard")
        return service.generate_chapter(pid, cid, body.writing_instruction,
                                        body.skill_id, body.skill_mode, body.selected_topic,
                                        state_context=state_context)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"AI 生成失败: {e}")

@app.post("/api/projects/{pid}/chapters/{cid}/summarize")
def api_summarize(pid: str, cid: str, user: dict = Depends(get_current_user)):
    guard_project(pid, user)
    try:
        return service.summarize_chapter(pid, cid)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"摘要生成失败: {e}")

@app.get("/api/skills")
def api_skills():
    return service.list_skills()

# ---------- 自主剧情 Agent ----------
@app.post("/api/projects/{pid}/chapters/{cid}/analyze")
def api_analyze_chapter(pid: str, cid: str, user: dict = Depends(get_current_user)):
    """分析一章 → 自动更新人物卡/世界设定/关系/伏笔/时间线"""
    guard_project(pid, user)
    try:
        return agent.analyze_chapter(pid, cid)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"章节分析失败: {e}")

@app.post("/api/projects/{pid}/sync")
def api_sync_project(pid: str, user: dict = Depends(get_current_user)):
    """启动全量同步（后台任务），返回任务状态；已运行则复用"""
    guard_project(pid, user)
    try:
        return agent.start_sync_project(pid)
    except Exception as e:
        raise HTTPException(500, f"启动全量同步失败: {e}")

@app.get("/api/projects/{pid}/sync-status")
def api_sync_status(pid: str, user: dict = Depends(get_current_user)):
    """查询全量同步进度"""
    guard_project(pid, user)
    return agent.get_sync_status(pid)

@app.post("/api/projects/{pid}/plan-next")
def api_plan_next(pid: str, body: dict | None = None, user: dict = Depends(get_current_user)):
    """基于完整记忆生成下一章规划"""
    guard_project(pid, user)
    try:
        instruction = (body or {}).get("instruction", "")
        return agent.plan_next_chapter(pid, instruction)
    except Exception as e:
        raise HTTPException(500, f"下一章规划失败: {e}")

@app.get("/api/projects/{pid}/story-state")
def api_story_state(pid: str, user: dict = Depends(get_current_user)):
    """作品状态包（结构化，含时间线/关系/伏笔）"""
    guard_project(pid, user)
    try:
        return agent.get_story_state(pid)
    except Exception as e:
        raise HTTPException(500, f"读取作品状态失败: {e}")

@app.get("/api/projects/{pid}/memory-stats")
def api_memory_stats(pid: str, user: dict = Depends(get_current_user)):
    """记忆统计（人物/时间线/关系/伏笔数量）"""
    guard_project(pid, user)
    try:
        return agent.memory_stats(pid)
    except Exception as e:
        raise HTTPException(500, f"读取记忆统计失败: {e}")

@app.get("/api/projects/{pid}/timeline")
def api_timeline(pid: str, user: dict = Depends(get_current_user)):
    guard_project(pid, user)
    return agent.get_story_state(pid)["timeline"]

@app.get("/api/projects/{pid}/relationships")
def api_relationships(pid: str, user: dict = Depends(get_current_user)):
    guard_project(pid, user)
    return agent.get_story_state(pid)["relationships"]

@app.delete("/api/projects/{pid}/relationships/{rid}")
def api_delete_relationship(pid: str, rid: str, user: dict = Depends(get_current_user)):
    """删除关系记录（人工修正）"""
    guard_project(pid, user)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM novel_relationship WHERE project_id=%s AND id=%s", (pid, rid))
        conn.commit()
    return {"ok": True}

@app.patch("/api/projects/{pid}/relationships/{rid}")
def api_update_relationship(pid: str, rid: str, body: dict, user: dict = Depends(get_current_user)):
    """人工修正关系记录"""
    guard_project(pid, user)
    allowed = ["relation", "sentiment", "trend", "note"]
    sets = []
    params = []
    for k in allowed:
        if k in body and body[k] is not None:
            sets.append(f"{k}=%s")
            params.append(body[k])
    if sets:
        sets.append("_updated_at=CURRENT_TIMESTAMP")
        params += [pid, rid]
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE novel_relationship SET {', '.join(sets)} WHERE project_id=%s AND id=%s RETURNING *", params)
                row = cur.fetchone()
            conn.commit()
        if not row:
            raise HTTPException(404, "关系记录不存在")
        return row
    raise HTTPException(400, "无可更新字段")

@app.get("/api/projects/{pid}/foreshadowing")
def api_foreshadowing(pid: str, user: dict = Depends(get_current_user)):
    guard_project(pid, user)
    state = agent.get_story_state(pid)
    return {"open": state["foreshadowing_open"], "resolved": state["foreshadowing_resolved"]}

@app.patch("/api/projects/{pid}/foreshadowing/{fid}")
def api_update_foreshadowing(pid: str, fid: str, body: dict, user: dict = Depends(get_current_user)):
    """人工标记伏笔状态（open/resolved）或修改描述"""
    guard_project(pid, user)
    allowed = ["description", "status", "type", "importance"]
    sets = []
    params = []
    for k in allowed:
        if k in body and body[k] is not None:
            sets.append(f"{k}=%s")
            params.append(body[k])
    if not sets:
        raise HTTPException(400, "无可更新字段")
    params += [pid, fid]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE novel_foreshadowing SET {', '.join(sets)} WHERE project_id=%s AND id=%s RETURNING *", params)
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise HTTPException(404, "伏笔记录不存在")
    return row

@app.delete("/api/projects/{pid}/foreshadowing/{fid}")
def api_delete_foreshadowing(pid: str, fid: str, user: dict = Depends(get_current_user)):
    guard_project(pid, user)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM novel_foreshadowing WHERE project_id=%s AND id=%s", (pid, fid))
        conn.commit()
    return {"ok": True}

@app.delete("/api/projects/{pid}/timeline/{tid}")
def api_delete_timeline(pid: str, tid: str, user: dict = Depends(get_current_user)):
    guard_project(pid, user)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM novel_timeline WHERE project_id=%s AND id=%s", (pid, tid))
        conn.commit()
    return {"ok": True}

# ---------- 静态前端 ----------
app.mount("/assets", StaticFiles(directory=FRONTEND_DIR), name="assets")

@app.get("/")
def index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.on_event("startup")
def startup():
    ensure_tables()
    # 清理历史孤儿记忆（删除章节但残留的记忆记录，如废稿章）
    try:
        cleaned = service.cleanup_all_orphan_memory()
        print(f"[启动] 孤儿记忆清理完成: {cleaned}")
    except Exception as e:
        print(f"[启动] 孤儿记忆清理失败（不影响服务）: {e}")
    if is_knowledge_empty():
        result = import_knowledge()
        print(f"[启动] 知识库为空，自动导入完成: {result}")
    else:
        print("[启动] 知识库已有数据，跳过导入")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT)
