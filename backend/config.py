import os


def get_env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default

    try:
        return int(value)
    except ValueError:
        raise ValueError(f"环境变量 {name} 必须是整数，当前值：{value}")


def get_env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


HOST = os.getenv("HOST", "127.0.0.1")
PORT = get_env_int("PORT", 8765)
NODE_ID = os.getenv("NODE_ID", "node_a")

HEARTBEAT_INTERVAL = get_env_int("HEARTBEAT_INTERVAL", 5)
HEARTBEAT_TIMEOUT = get_env_int("HEARTBEAT_TIMEOUT", 5)

JWT_SECRET = os.getenv("JWT_SECRET", "dev_only_change_me")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXP_HOURS = get_env_int("JWT_EXP_HOURS", 1)
TOKEN_REFRESH_WINDOW_SECONDS = get_env_int("TOKEN_REFRESH_WINDOW_SECONDS", 600)

REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = get_env_int("REDIS_PORT", 6379)
REDIS_DB = get_env_int("REDIS_DB", 0)
REDIS_OFFLINE_TTL_SECONDS = get_env_int("REDIS_OFFLINE_TTL_SECONDS", 7 * 24 * 60 * 60)
REDIS_KEY_PREFIX = os.getenv("REDIS_KEY_PREFIX", "chat")

ONLINE_STATUS_TTL_SECONDS = get_env_int("ONLINE_STATUS_TTL_SECONDS", 15)
ONLINE_STATUS_RENEW_INTERVAL_SECONDS = get_env_int("ONLINE_STATUS_RENEW_INTERVAL_SECONDS", 5)
DEDUPE_TTL_SECONDS = get_env_int("DEDUPE_TTL_SECONDS", 10 * 60)

# 用户存储路径（JSON 文件，用于 user_store 持久化）
USER_STORE_PATH = os.getenv("USER_STORE_PATH", "./data/users.json")

ENABLE_TEST_SEED = get_env_bool("ENABLE_TEST_SEED", True)

TEST_ACCOUNTS = {
    "user001": "123456",
    "user002": "654321",
    "user003": "111111",
    "user004": "222222",
    "admin": "admin123",
}