import os

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8765"))
NODE_ID = os.getenv("NODE_ID", "node_a")

HEARTBEAT_INTERVAL = 5
HEARTBEAT_TIMEOUT = 5

JWT_SECRET = os.getenv("JWT_SECRET", "dev_only_change_me")
JWT_ALGORITHM = "HS256"
JWT_EXP_HOURS = 1
TOKEN_REFRESH_WINDOW_SECONDS = 600

REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_OFFLINE_TTL_SECONDS = 7 * 24 * 60 * 60
REDIS_KEY_PREFIX = "chat"

ONLINE_STATUS_TTL_SECONDS = 15
ONLINE_STATUS_RENEW_INTERVAL_SECONDS = 5

TEST_ACCOUNTS = {
    "user001": "123456",
    "user002": "654321",
    "user003": "111111",
    "user004": "222222",
    "admin": "admin123",
}