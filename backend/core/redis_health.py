from backend.core.redis_client import redis_client
from backend.config import REDIS_KEY_PREFIX
from backend.utils.logger import logger


def check_redis_health() -> None:
    """
    启动阶段 Redis 健康检查。

    目标：
    1. Redis 能连接
    2. Redis 能读写
    3. Pub/Sub 基础订阅能力可用

    任意一步失败，直接抛异常，让服务启动失败。
    """
    health_key = f"{REDIS_KEY_PREFIX}:healthcheck"
    pubsub_channel = f"{REDIS_KEY_PREFIX}:healthcheck:pubsub"

    logger.info("开始 Redis 健康检查")

    redis_client.ping()

    redis_client.set(health_key, "ok", ex=10)
    value = redis_client.get(health_key)
    if value != "ok":
        raise RuntimeError("Redis 读写健康检查失败")

    pubsub = redis_client.pubsub(ignore_subscribe_messages=True)
    try:
        pubsub.subscribe(pubsub_channel)
        pubsub.unsubscribe(pubsub_channel)
    finally:
        pubsub.close()

    logger.info("Redis 健康检查通过")