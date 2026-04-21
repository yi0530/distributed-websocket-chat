import asyncio
import signal

import websockets

import backend.core.state as state_module
from backend.config import HOST, PORT, JWT_SECRET
from backend.core.connection import check_connection_auth, handle_client, handle_exit
from backend.utils.logger import logger


async def main():
    if JWT_SECRET == "dev_only_change_me":
        logger.warning("当前 JWT_SECRET 使用开发默认值，部署前请改为环境变量")

    state_module.server = await websockets.serve(
        handle_client,
        HOST,
        PORT,
        process_request=check_connection_auth,
    )

    logger.info("=" * 60)
    logger.info("WebSocket 聊天服务已启动")
    logger.info("地址：ws://%s:%s", HOST, PORT)
    logger.info("=" * 60)

    await state_module.server.wait_closed()


if __name__ == "__main__":
    signal.signal(signal.SIGINT, handle_exit)
    asyncio.run(main())