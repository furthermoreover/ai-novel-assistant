# -*- coding: utf-8 -*-
"""作者账号：注册 / 登录 / Token 认证（标准库实现，无第三方依赖）"""
import base64
import hashlib
import hmac
import json
import time
import uuid

from db import get_conn

# 本地单机工具：固定密钥用于签名 token（如需更安全可改为环境变量）
SECRET = b"ai-novel-assistant-local-secret-2026-v1"
TOKEN_TTL = 30 * 24 * 3600  # 30 天


# ---------- 密码哈希（PBKDF2） ----------
def hash_password(password: str) -> str:
    salt = hashlib.sha256(os_urandom(16)).digest()
    iterations = 100_000
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2${iterations}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


def os_urandom(n: int) -> bytes:
    import os
    return os.urandom(n)


# ---------- Token（payload.signature） ----------
def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def create_token(user_id: str) -> str:
    payload = json.dumps({"uid": str(user_id), "exp": int(time.time()) + TOKEN_TTL}).encode()
    sig = hmac.new(SECRET, payload, hashlib.sha256).hexdigest()
    return _b64e(payload) + "." + sig


def verify_token(token: str) -> dict | None:
    """校验 token，成功返回 user 字典，失败返回 None"""
    try:
        payload_b64, sig = token.split(".", 1)
        payload = _b64d(payload_b64)
        expect = hmac.new(SECRET, payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expect, sig):
            return None
        data = json.loads(payload)
        if data.get("exp", 0) < time.time():
            return None
        return get_user(data["uid"])
    except Exception:
        return None


def get_user(user_id: str) -> dict | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, _created_at AS created_at FROM author_user WHERE id=%s",
                (user_id,),
            )
            return cur.fetchone()


# ---------- 注册 / 登录 ----------
def register(username: str, password: str) -> dict:
    """注册作者账号。首个注册的用户自动接管所有未归属项目。"""
    username = (username or "").strip()
    if not username or len(username) < 2 or len(username) > 32:
        raise ValueError("用户名需为 2-32 个字符")
    if not password or len(password) < 6:
        raise ValueError("密码至少 6 位")
    uid = str(uuid.uuid4())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM author_user WHERE username=%s", (username,))
            if cur.fetchone():
                raise ValueError("用户名已被注册")
            cur.execute(
                "INSERT INTO author_user (id, username, password_hash) VALUES (%s,%s,%s) RETURNING *",
                (uid, username, hash_password(password)),
            )
            user = cur.fetchone()
            # 首个注册用户自动接管未归属项目
            cur.execute("SELECT COUNT(*) AS n FROM author_user")
            if cur.fetchone()["n"] == 1:
                cur.execute("UPDATE novel_project SET user_id=%s WHERE user_id IS NULL", (uid,))
        conn.commit()
    return {"id": str(user["id"]), "username": user["username"]}


def login(username: str, password: str) -> dict:
    username = (username or "").strip()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM author_user WHERE username=%s", (username,))
            row = cur.fetchone()
    if not row or not verify_password(password, row["password_hash"]):
        raise ValueError("用户名或密码错误")
    return {"id": str(row["id"]), "username": row["username"]}
