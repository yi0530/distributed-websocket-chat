import os

HOST = "127.0.0.1"
PORT = 8765

HEARTBEAT_INTERVAL = 5
HEARTBEAT_TIMEOUT = 5

JWT_SECRET = os.getenv("JWT_SECRET", "dev_only_change_me")
JWT_ALGORITHM = "HS256"
JWT_EXP_HOURS = 1
TOKEN_REFRESH_WINDOW_SECONDS = 600

TEST_ACCOUNTS = {
    "user001": "123456",
    "user002": "654321",
    "user003": "111111",
    "user004": "222222",
    "user005": "333333",
    "user006": "444444",
    "admin": "admin123",
}

