from backend.core.protocol import build_message, send_json
from backend.core.state import connections


async def handle_get_online_users(websocket, proto: dict):
    msg_id = proto.get("msg_id")

    online_users = sorted({
        ctx.user_id
        for ctx in connections.values()
        if ctx.is_authenticated and ctx.user_id
    })

    await send_json(
        websocket,
        build_message(
            "online_users",
            msg_id=msg_id,
            code=200,
            content=online_users,
        ),
    )