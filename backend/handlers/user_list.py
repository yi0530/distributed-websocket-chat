import asyncio

from backend.core.protocol import build_message, send_json
from backend.core.state import connections
from backend.core.online_registry_service import list_all_online_users


async def handle_get_online_users(websocket, proto: dict):
    msg_id = proto.get("msg_id")

    online_users = sorted({
        ctx.user_id
        for ctx in connections.values()
        if ctx.is_authenticated and ctx.user_id
    })

    # Merge with Redis online registry for cross-node visibility
    try:
        redis_users = await asyncio.to_thread(list_all_online_users)
        online_users = sorted(set(online_users) | set(redis_users))
    except Exception:
        pass

    await send_json(
        websocket,
        build_message(
            "online_users",
            msg_id=msg_id,
            code=200,
            content=online_users,
        ),
    )