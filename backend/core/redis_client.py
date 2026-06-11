import redis

from backend.config import REDIS_DB, REDIS_HOST, REDIS_PORT

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    decode_responses=True,
    protocol=2,
    socket_connect_timeout=0.5,
    socket_timeout=0.5,
    socket_keepalive=True,
    health_check_interval=0,
    retry_on_timeout=False,
)