import asyncio

from backend.config import NODE_ID, ONLINE_STATUS_RENEW_INTERVAL_SECONDS
from backend.core.online_registry_service import (
    clear_user_online,
    refresh_user_online,
    set_user_online,
)
from backend.core.state import connections
from backend.utils.logger import logger


async def _online_status_renew_task(websocket):
    while True:
        await asyncio.sleep(ONLINE_STATUS_RENEW_INTERVAL_SECONDS)

        ctx = connections.get(websocket)
        if ctx is None:
            break

        if not ctx.is_authenticated or not ctx.user_id:
            break

        try:
            ok = await asyncio.to_thread(refresh_user_online, ctx.user_id, NODE_ID)
        except Exception:
            logger.exception("在线状态续命异常：user=%s node=%s", ctx.user_id, NODE_ID)
            break
        if not ok:
            logger.warning("在线状态续命失败：user=%s node=%s", ctx.user_id, NODE_ID)
            break


async def start_online_presence(websocket) -> None:
    ctx = connections.get(websocket)
    if ctx is None:
        return
    if not ctx.is_authenticated or not ctx.user_id:
        return

    await asyncio.to_thread(set_user_online, ctx.user_id, NODE_ID)

    if ctx.online_status_task is not None:
        ctx.online_status_task.cancel()

    ctx.online_status_task = asyncio.create_task(_online_status_renew_task(websocket))


async def stop_online_presence(websocket) -> None:
    ctx = connections.get(websocket)
    if ctx is None:
        return

    if ctx.online_status_task is not None:
        ctx.online_status_task.cancel()
        try:
            await ctx.online_status_task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("清理在线状态续命任务失败")

    if ctx.user_id:
        try:
            await asyncio.to_thread(clear_user_online, ctx.user_id, NODE_ID)
        except Exception:
            logger.exception("清理在线状态失败：user=%s node=%s", ctx.user_id, NODE_ID)