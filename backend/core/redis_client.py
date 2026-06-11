import redis

from backend.config import REDIS_DB, REDIS_HOST, REDIS_PORT

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    decode_responses=True,
    socket_connect_timeout=1,
    socket_timeout=1,
    socket_keepalive=True,
    health_check_interval=10,
    retry_on_timeout=False,
)