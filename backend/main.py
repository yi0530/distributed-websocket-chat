import asyncio
import signal

import websockets

import backend.core.state as state_module
from backend.config import HOST, PORT, JWT_SECRET, NODE_ID
from backend.core.connection import check_connection_auth, handle_client, handle_exit
from backend.utils.logger import logger
from backend.core.pubsub_service import start_pubsub_listener
from backend.core.conversation_service import seed_test_conversations_once


async def main():
    if JWT_SECRET == "dev_only_change_me":
        logger.warning("当前 JWT_SECRET 使用开发默认值，部署前请改为环境变量")

    seed_test_conversations_once()

    state_module.server = await websockets.serve(
        handle_client,
        HOST,
        PORT,
        process_request=check_connection_auth,
    )

    start_pubsub_listener(asyncio.get_running_loop())

    logger.info("=" * 60)
    logger.info("WebSocket 聊天服务已启动")
    logger.info("地址：ws://%s:%s", HOST, PORT)
    logger.info("=" * 60)
    logger.info("节点ID：%s", NODE_ID)

    await state_module.server.wait_closed()


if __name__ == "__main__":
    signal.signal(signal.SIGINT, handle_exit)
    asyncio.run(main())