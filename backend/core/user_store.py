"""
最小用户持久化存储。

基于 JSON 文件，使用 PBKDF2-SHA256 存储密码哈希。
登录和注册统一调用本模块，替换旧的 TEST_ACCOUNTS 硬编码校验。
"""

import hashlib
import hmac
import json
import os
import re
import secrets
import time
from pathlib import Path

from backend.config import ENABLE_TEST_SEED, TEST_ACCOUNTS, USER_STORE_PATH
from backend.utils.logger import logger

# 密码哈希参数
_PBKDF2_ITERATIONS = 100_000
_PBKDF2_HASH = "sha256"
_SALT_BYTES = 16

# 用户名 / 密码规则
_RE_USERNAME = re.compile(r"^[A-Za-z0-9_]{3,32}$")
_MIN_PASSWORD_LEN = 6
_MAX_PASSWORD_LEN = 128

# 项目根目录（用于解析相对路径）
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

_users: dict[str, dict] = {}          # 内存缓存
_store_path: Path | None = None
_initialized = False


def get_user_store_path() -> Path:
    """返回用户存储文件的解析后的绝对路径。"""
    p = Path(USER_STORE_PATH)
    if not p.is_absolute():
        p = (_PROJECT_ROOT / p).resolve()
    return p


# ── 初始化 ────────────────────────────────────────────────────────

def init_user_store():
    global _initialized, _store_path, _users
    if _initialized:
        return

    _store_path = get_user_store_path()
    _store_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("用户存储路径：%s", _store_path)

    # 读取已有用户，不存在则创建空文件
    if _store_path.exists():
        try:
            _users = json.loads(_store_path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("用户存储文件读取失败，使用空用户表")
            _users = {}
    else:
        _users = {}

    # 测试账号种子写入
    if ENABLE_TEST_SEED and TEST_ACCOUNTS:
        any_new = False
        for username, password in TEST_ACCOUNTS.items():
            if username not in _users:
                # 测试账号使用固定 salt（确定性种子），方便课程演示
                salt = secrets.token_hex(_SALT_BYTES)
                _users[username] = {
                    "password_hash": _hash_password(password, salt),
                    "salt": salt,
                    "created_at": int(time.time()),
                }
                any_new = True
        if any_new:
            _write_users()
            logger.info("已写入测试账号种子：%d 个用户", len(TEST_ACCOUNTS))
        else:
            logger.info("测试账号已存在，跳过种子写入")

    _initialized = True


# ── 密码哈希 ──────────────────────────────────────────────────────

def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        _PBKDF2_HASH,
        password.encode("utf-8"),
        salt.encode("utf-8"),
        _PBKDF2_ITERATIONS,
    ).hex()


# ── 用户 CRUD ─────────────────────────────────────────────────────

def create_user(username: str, password: str) -> None:
    if not _initialized:
        init_user_store()

    validate_username(username)
    validate_password(password)

    if user_exists(username):
        raise ValueError("用户名已存在")

    salt = secrets.token_hex(_SALT_BYTES)
    _users[username] = {
        "password_hash": _hash_password(password, salt),
        "salt": salt,
        "created_at": int(time.time()),
    }
    _write_users()
    logger.info("用户注册成功：%s", username)


def verify_user(username: str, password: str) -> bool:
    if not _initialized:
        init_user_store()

    record = _users.get(username)
    if not record:
        return False

    expected_hash = _hash_password(password, record["salt"])
    return hmac.compare_digest(expected_hash, record["password_hash"])


def user_exists(username: str) -> bool:
    if not _initialized:
        init_user_store()
    return username in _users


def validate_username(username: str) -> None:
    if not isinstance(username, str):
        raise ValueError("用户名必须是字符串")
    if not _RE_USERNAME.match(username):
        raise ValueError("用户名格式非法：3-32位字母、数字或下划线")


def validate_password(password: str) -> None:
    if not isinstance(password, str):
        raise ValueError("密码必须是字符串")
    if len(password) < _MIN_PASSWORD_LEN or len(password) > _MAX_PASSWORD_LEN:
        raise ValueError(f"密码长度必须在 {_MIN_PASSWORD_LEN}-{_MAX_PASSWORD_LEN} 位之间")


# ── 持久化 ────────────────────────────────────────────────────────

def _write_users():
    if _store_path is None:
        return
    try:
        data = json.dumps(_users, ensure_ascii=False, indent=2)
        tmp_path = _store_path.with_suffix(".tmp")
        tmp_path.write_text(data, encoding="utf-8")
        os.replace(tmp_path, _store_path)
    except Exception:
        logger.exception("用户存储写入失败")
