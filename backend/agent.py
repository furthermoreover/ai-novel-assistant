# -*- coding: utf-8 -*-
"""自主剧情 Agent：章节分析 → 记忆更新 → 下一章规划 → 状态包注入

职责：
1. analyze_chapter  读章节，用 LLM 抽取结构化信息（事件/人物状态/设定/关系/伏笔/悬念）
2. apply_analysis   把抽取结果增量合并进数据库（人物卡/世界设定/关系图/时间线/伏笔库）
3. sync_project     （可选）全量分析未同步章节
4. plan_next_chapter 基于完整记忆生成下一章规划（大纲）
5. get_story_state / story_state_text 组装"作品状态包"（分精简/深度两档，控制 token）
"""
import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone

from db import get_conn
from ai import chat_completion
from config import SUMMARIZE_MODEL
import service

_PROMPT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompts")
_PROMPT_CACHE: dict[str, str] = {}


def _read_prompt(name: str) -> str:
    """读取 prompts/ 下的提示词文件（带缓存）"""
    if name not in _PROMPT_CACHE:
        path = os.path.join(_PROMPT_DIR, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                _PROMPT_CACHE[name] = f.read().strip()
        except Exception:
            _PROMPT_CACHE[name] = "你是一位小说分析助手。"
    return _PROMPT_CACHE[name]


def _clean_json(text: str) -> dict:
    """清洗 LLM 输出中的 JSON（去除 ```json 包裹与前后废话）"""
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # 尝试修复：去掉行尾多余的逗号
        text = re.sub(r",\s*([}\]])", r"\1", text)
        data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("模型输出不是有效的 JSON 对象，请重试本章分析")
    return data


# ---------- 1. 章节分析 ----------
def analyze_chapter(pid: str, cid: str, force: bool = False) -> dict:
    """分析一章，返回结构化 JSON + 已应用结果"""
    chapter = service.get_chapter(pid, cid)
    if not chapter:
        raise ValueError("章节不存在")
    content = chapter.get("content") or ""
    if not content:
        raise ValueError("章节内容为空，无法分析")

    # 既有记忆（供判断新增/变化）
    existing = _existing_memory_text(pid)

    system = _read_prompt("agent_analyze.md")
    user = (
        f"【本章正文】\n第{chapter['chapter_number']}章 {chapter['title']}\n\n{content[:12000]}\n\n"
        f"【既有记忆】\n{existing or '（暂无既有记忆）'}\n\n"
        f"请按你的输出格式，输出本章的结构化分析 JSON。"
    )
    raw = chat_completion(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        model=SUMMARIZE_MODEL, temperature=0.2, max_tokens=2048,
    )
    analysis = _clean_json(raw)

    result = apply_analysis(pid, cid, analysis)
    result["analysis"] = analysis
    return result


def _existing_memory_text(pid: str) -> str:
    """拼一段简短的既有记忆摘要（供分析器判断变化）"""
    outline = service.get_outline(pid)
    chars = service.list_characters(pid)
    parts = []
    if outline and outline.get("world_setting"):
        parts.append(f"【世界设定】\n{outline['world_setting'][:800]}")
    if chars:
        blocks = [f"{c['name']}：{c.get('identity') or ''}｜{c.get('current_status') or c.get('background') or ''}"[:120] for c in chars]
        parts.append("【人物】\n" + "\n".join(blocks))
    return "\n\n".join(parts)


# ---------- 2. 应用分析结果到数据库 ----------
# 全量同步并发分析时，写库必须串行化：
#   LLM 调用（慢）可并行；apply_analysis 的"查重→写入"必须在同一把锁内串行，
#   否则两个线程会同时 SELECT 到"角色不存在"再各自 INSERT，产生重复人物卡。
_APPLY_LOCK = threading.Lock()


def apply_analysis(pid: str, cid: str, analysis: dict) -> dict:
    """把分析 JSON 增量合并进数据库，返回各项处理计数"""
    if not isinstance(analysis, dict):
        raise ValueError("分析结果不是有效 JSON 对象")
    chapter = service.get_chapter(pid, cid)
    if not chapter:
        raise ValueError("章节不存在")
    num = chapter["chapter_number"]
    counts = {"characters": 0, "world": 0, "relationships": 0,
              "foreshadowing_planted": 0, "foreshadowing_resolved": 0, "timeline": 0}

    with _APPLY_LOCK:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # --- 人物卡更新/创建 ---
                for ch in analysis.get("characters", []) or []:
                    name = (ch.get("name") or "").strip()
                    if not name:
                        continue
                    status = (ch.get("current_status") or "").strip()
                    motivation = (ch.get("motivation") or "").strip()
                    new_info = (ch.get("new_info") or "").strip()
                    # 查找现有角色
                    cur.execute("SELECT id FROM novel_character WHERE project_id=%s AND name=%s", (pid, name))
                    row = cur.fetchone()
                    if row:
                        sets, params = ["_updated_at=CURRENT_TIMESTAMP"], []
                        if status:
                            sets.append("current_status=%s"); params.append(status)
                        if motivation:
                            sets.append("motivation=%s"); params.append(motivation)
                        if new_info:
                            cur.execute("SELECT other_info FROM novel_character WHERE id=%s", (row["id"],))
                            old = (cur.fetchone() or {}).get("other_info") or ""
                            merged = f"{old}\n【第{num}章】{new_info}".strip() if old.strip() else f"【第{num}章】{new_info}"
                            sets.append("other_info=%s"); params.append(merged)
                        sets.append("last_appearance_chapter=%s"); params.append(num)
                        params += [row["id"]]
                        cur.execute(f"UPDATE novel_character SET {', '.join(sets)} WHERE id=%s", params)
                    else:
                        cid_new = str(uuid.uuid4())
                        cur.execute(
                            """INSERT INTO novel_character
                               (id, project_id, name, current_status, motivation, other_info, last_appearance_chapter)
                               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                            (cid_new, pid, name, status or "", motivation or "",
                             f"【第{num}章】首次登场：{new_info}" if new_info else f"【第{num}章】首次登场", num),
                        )
                    counts["characters"] += 1

                # --- 世界设定（追加到 outline.world_setting） ---
                world_updates = analysis.get("world_updates", []) or []
                if world_updates:
                    cur.execute("SELECT world_setting FROM novel_outline WHERE project_id=%s", (pid,))
                    row = cur.fetchone()
                    old_ws = (row or {}).get("world_setting") or ""
                    additions = []
                    for w in world_updates:
                        cat = w.get("category") or "其他"
                        item = (w.get("item") or "").strip()
                        update = (w.get("update") or "").strip()
                        if item and update:
                            additions.append(f"【第{num}章·{cat}】{item}：{update}")
                    if additions:
                        new_ws = (old_ws.rstrip() + "\n\n" + "\n".join(additions)) if old_ws.strip() else "\n".join(additions)
                        cur.execute("UPDATE novel_outline SET world_setting=%s, _updated_at=CURRENT_TIMESTAMP WHERE project_id=%s", (new_ws, pid))
                        counts["world"] = len(additions)

                # --- 人物关系（upsert） ---
                for r in analysis.get("relationships", []) or []:
                    a = (r.get("char_a") or "").strip()
                    b = (r.get("char_b") or "").strip()
                    if not a or not b or a == b:
                        continue
                    key_a, key_b = sorted([a, b])
                    relation = (r.get("relation") or "").strip()
                    sentiment = r.get("sentiment") or "neutral"
                    trend = r.get("trend") or "stable"
                    note = (r.get("note") or "").strip()
                    cur.execute(
                        """INSERT INTO novel_relationship
                           (project_id, char_a, char_b, relation, sentiment, trend, last_change_chapter, note)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                           ON CONFLICT (project_id, char_a, char_b)
                           DO UPDATE SET relation=EXCLUDED.relation,
                                         sentiment=EXCLUDED.sentiment,
                                         trend=EXCLUDED.trend,
                                         last_change_chapter=EXCLUDED.last_change_chapter,
                                         note=EXCLUDED.note,
                                         _updated_at=CURRENT_TIMESTAMP""",
                        (pid, key_a, key_b, relation, sentiment, trend, num, note),
                    )
                    counts["relationships"] += 1

                # --- 伏笔：埋设 ---
                for f in analysis.get("foreshadowing_planted", []) or []:
                    desc = (f.get("description") or "").strip()
                    if not desc:
                        continue
                    ftype = f.get("type") or "other"
                    imp = f.get("importance") or "medium"
                    cur.execute(
                        """INSERT INTO novel_foreshadowing
                           (project_id, description, type, status, planted_chapter, importance)
                           VALUES (%s,%s,%s,'open',%s,%s)""",
                        (pid, desc, ftype, num, imp),
                    )
                    counts["foreshadowing_planted"] += 1

                # --- 伏笔：回收（匹配 open 伏笔） ---
                for f in analysis.get("foreshadowing_resolved", []) or []:
                    desc = (f.get("description") or "").strip()
                    if not desc:
                        continue
                    cur.execute(
                        """SELECT id, description FROM novel_foreshadowing
                           WHERE project_id=%s AND status='open'
                           ORDER BY _created_at ASC""", (pid,),
                    )
                    candidates = cur.fetchall()
                    words = [w for w in re.split(r"[，。！？、\s：；]", desc) if len(w) >= 2]
                    best = None
                    for cand in candidates:
                        full = cand.get("description") or ""
                        if any(w and w in full for w in words[:3]):
                            best = cand["id"]
                            break
                    if best:
                        cur.execute(
                            "UPDATE novel_foreshadowing SET status='resolved', resolved_chapter=%s WHERE id=%s",
                            (num, best),
                        )
                        counts["foreshadowing_resolved"] += 1

                # --- 时间线 ---
                location = (analysis.get("location") or "").strip()
                events = analysis.get("events", []) or []
                ch_names = [c.get("name") for c in (analysis.get("characters", []) or []) if c.get("name")]
                if events or location:
                    cur.execute(
                        """INSERT INTO novel_timeline (project_id, chapter_number, location, events, characters)
                           VALUES (%s,%s,%s,%s,%s)""",
                        (pid, num, location, "\n".join(events), ch_names),
                    )
                    counts["timeline"] = 1

                # --- 摘要填充（为空才填） ---
                if not (chapter.get("summary") or "").strip():
                    summ = (analysis.get("chapter_summary") or "").strip()
                    if summ:
                        cur.execute(
                            "UPDATE novel_chapter SET summary=%s, _updated_at=CURRENT_TIMESTAMP WHERE id=%s",
                            (summ, cid),
                        )
            conn.commit()
    return {"applied": counts, "chapter_number": num}


# ---------- 3. 全量同步（后台任务 + 进度追踪） ----------
SYNC_TASKS: dict[str, dict] = {}
_SYNC_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def start_sync_project(pid: str) -> dict:
    """启动全量同步后台任务，立即返回任务状态（含进度）"""
    with _SYNC_LOCK:
        existing = SYNC_TASKS.get(pid)
        if existing and existing.get("status") == "running":
            return existing
        chapters = service.list_chapters(pid)["items"]
        pending = []
        with get_conn() as conn:
            with conn.cursor() as cur:
                for c in chapters:
                    cur.execute(
                        "SELECT 1 FROM novel_timeline WHERE project_id=%s AND chapter_number=%s",
                        (pid, c["chapter_number"]),
                    )
                    if cur.fetchone():
                        continue
                    if (c.get("content") or "").strip():
                        pending.append(c["chapter_number"])
        task = {
            "pid": pid,
            "status": "running",
            "total": len(pending),
            "done": 0,
            "current_chapter": None,
            "synced": [],
            "errors": [],
            "started_at": _now_iso(),
            "finished_at": None,
        }
        SYNC_TASKS[pid] = task
        t = threading.Thread(target=_run_sync, args=(pid, pending, task), daemon=True)
        t.start()
        return task


def _run_sync(pid: str, pending: list[int], task: dict) -> None:
    """后台任务：并发分析待同步章节（默认 3 路），更新进度。

    LLM 调用（主要耗时）并行；写库在 apply_analysis 内由 _APPLY_LOCK 串行化，
    既提速又避免并发"查重→插入"产生重复人物卡。
    """
    import concurrent.futures

    try:
        chapters = {c["chapter_number"]: c["id"] for c in service.list_chapters(pid)["items"]}

        def work(num: int) -> None:
            cid = chapters.get(num)
            with _SYNC_LOCK:
                task["current_chapter"] = num
            try:
                if cid:
                    analyze_chapter(pid, cid)
                with _SYNC_LOCK:
                    task["synced"].append(num)
            except Exception as e:
                with _SYNC_LOCK:
                    task["errors"].append(f"第{num}章: {e}")
            finally:
                with _SYNC_LOCK:
                    task["done"] += 1

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
            list(ex.map(work, pending))
        task["status"] = "done"
    except Exception as e:
        task["status"] = "error"
        task["errors"].append(str(e))
    finally:
        task["current_chapter"] = None
        task["finished_at"] = _now_iso()


def get_sync_status(pid: str) -> dict:
    """查询同步任务进度"""
    task = SYNC_TASKS.get(pid)
    if not task:
        return {"status": "idle", "total": 0, "done": 0, "current_chapter": None,
                "synced": [], "errors": [], "started_at": None, "finished_at": None}
    return task


# ---------- 4. 作品状态包（分档控制 token） ----------
def get_story_state(pid: str) -> dict:
    """组装完整作品状态（结构化，供前端展示与深度注入）"""
    project = service.get_project(pid)
    outline = service.get_outline(pid)
    chars = service.list_characters(pid)
    chapters = service.list_chapters(pid)["items"]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM novel_timeline WHERE project_id=%s ORDER BY chapter_number", (pid,))
            timeline = cur.fetchall()
            cur.execute("SELECT * FROM novel_relationship WHERE project_id=%s ORDER BY char_a, char_b", (pid,))
            relationships = cur.fetchall()
            cur.execute("SELECT * FROM novel_foreshadowing WHERE project_id=%s AND status='open' ORDER BY planted_chapter", (pid,))
            open_foreshadowing = cur.fetchall()
            cur.execute("SELECT * FROM novel_foreshadowing WHERE project_id=%s AND status='resolved' ORDER BY resolved_chapter", (pid,))
            resolved_foreshadowing = cur.fetchall()
    recent = chapters[-3:] if chapters else []
    return {
        "project": project,
        "outline": outline,
        "characters": chars,
        "chapters": chapters,
        "timeline": timeline,
        "relationships": relationships,
        "foreshadowing_open": open_foreshadowing,
        "foreshadowing_resolved": resolved_foreshadowing,
        "recent_chapters": recent,
    }


def story_state_text(pid: str, mode: str = "standard") -> str:
    """作品状态包文本。

    mode="standard"：精简动态层（默认，控制 ~2-3k token）——
      主线前500字、人物一行卡（身份+当前状态）、最近3章摘要、
      未回收伏笔、关系图（≤15条）、时间线（最近5条）。
    mode="deep"：完整层——全量大纲、人物全文、完整时间线/关系/伏笔。
    """
    state = get_story_state(pid)
    parts = []
    o = state.get("outline") or {}

    if mode == "deep":
        labels = [("main_storyline", "主线剧情"), ("world_setting", "世界设定"), ("volume_plans", "分卷规划"),
                  ("key_plot_points", "关键情节"), ("foreshadowing", "伏笔"), ("other_notes", "其他备注")]
        blocks = [f"【{label}】\n{o.get(key) or ''}" for key, label in labels if o.get(key)]
        if blocks:
            parts.append("## 大纲\n" + "\n\n".join(blocks))
    else:
        # 精简：主线前500字
        mainline = (o.get("main_storyline") or "").strip()
        if mainline:
            parts.append("## 主线\n" + mainline[:500])
        ws = (o.get("world_setting") or "").strip()
        if ws:
            parts.append("## 世界设定（摘要）\n" + ws[:300])

    # 人物卡
    chars = state.get("characters") or []
    if mode == "deep":
        blocks = []
        for c in chars:
            lines = [f"===== {c['name']} ====="]
            for key, label in [("identity", "身份"), ("current_status", "当前状态"),
                               ("motivation", "动机"), ("personality", "性格"),
                               ("background", "背景"), ("relationships", "人物关系"),
                               ("speech_style", "说话风格"), ("appearance", "外貌")]:
                if c.get(key):
                    lines.append(f"{label}：{c[key]}")
            if c.get("other_info"):
                lines.append(f"动态记录：{c['other_info']}")
            blocks.append("\n".join(lines))
        parts.append("## 人物卡（含最新状态）\n" + "\n\n".join(blocks))
    else:
        # 精简一行卡：名字｜身份｜当前状态（只注入最关键的动态字段）
        lines = []
        for c in chars[:15]:
            ident = (c.get("identity") or "").strip()
            status = (c.get("current_status") or "").strip()
            if status:
                lines.append(f"{c['name']}｜{ident}｜{status}")
            elif ident:
                lines.append(f"{c['name']}｜{ident}")
            else:
                lines.append(f"{c['name']}")
        if lines:
            parts.append("## 人物（一行卡）\n" + "\n".join(lines))

    # 关系图
    rels = state.get("relationships") or []
    rels_show = rels[:15] if mode == "standard" else rels
    if rels_show:
        lines = [f"{r['char_a']} — {r['char_b']}：{r.get('relation') or ''}（{r.get('sentiment') or 'neutral'}，{r.get('trend') or 'stable'}）" for r in rels_show]
        parts.append("## 人物关系\n" + "\n".join(lines))

    # 时间线（标准只最近5条）
    tl = state.get("timeline") or []
    tl_show = tl[-5:] if mode == "standard" else tl
    if tl_show:
        lines = [f"第{t['chapter_number']}章@{t.get('location') or '?'}：{(t.get('events') or '')[:150]}" for t in tl_show]
        parts.append("## 剧情时间线\n" + "\n".join(lines))

    # 伏笔：只注入未回收（已回收的不注入，省 token）
    of = state.get("foreshadowing_open") or []
    if of:
        lines = [f"（第{f['planted_chapter']}章埋）{f['description']}" for f in of]
        parts.append("## 未回收伏笔\n" + "\n".join(lines))
    if mode == "deep":
        rf = state.get("foreshadowing_resolved") or []
        if rf:
            lines = [f"（第{f['planted_chapter']}章埋，第{f['resolved_chapter']}章回收）{f['description']}" for f in rf]
            parts.append("## 已回收伏笔\n" + "\n".join(lines))

    # 最近章节摘要
    rc = state.get("recent_chapters") or []
    if rc:
        lines = [f"第{c['chapter_number']}章 {c['title']}\n摘要：{c.get('summary') or ''}" for c in rc]
        parts.append("## 最近章节摘要\n" + "\n\n".join(lines))

    return "\n\n".join(parts)


# ---------- 5. 下一章规划 ----------
def plan_next_chapter(pid: str, instruction: str = "") -> dict:
    """基于完整记忆生成下一章规划（大纲）"""
    state_text = story_state_text(pid, mode="deep")[:16000]
    chapters = service.list_chapters(pid)["items"]
    latest = chapters[-1] if chapters else None
    system = _read_prompt("agent_plan.md")
    user = (
        f"【作品状态包】\n{state_text}\n\n"
        f"【最新章节结尾】\n第{latest['chapter_number']}章 {latest['title']}\n"
        f"{(latest.get('content') or '')[-2500:] if latest else '（无）'}\n\n"
        f"【用户指令】\n{instruction or '（无，请基于当前剧情自主判断下一章该写什么）'}\n\n"
        f"请输出下一章规划。"
    )
    plan = chat_completion(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        model=SUMMARIZE_MODEL, temperature=0.5, max_tokens=2048,
    ).strip()
    next_num = (latest["chapter_number"] + 1) if latest else 1
    # 解析建议章节名（格式：本章标题（建议）：xxx）
    title = None
    m = re.search(r"本章标题\s*[（(]建议[）)]\s*[：:]\s*(.+)", plan)
    if m:
        title = m.group(1).strip().strip(r"，。,.、\s")
    if not title:
        title = f"第{next_num}章"
    return {"chapter_number": next_num, "title": title, "plan": plan}


# ---------- 6. 记忆统计 ----------
def memory_stats(pid: str) -> dict:
    state = get_story_state(pid)
    return {
        "characters": len(state.get("characters") or []),
        "timeline": len(state.get("timeline") or []),
        "relationships": len(state.get("relationships") or []),
        "foreshadowing_open": len(state.get("foreshadowing_open") or []),
        "foreshadowing_resolved": len(state.get("foreshadowing_resolved") or []),
        "chapters": len(state.get("chapters") or []),
    }
