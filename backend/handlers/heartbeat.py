from backend.core.protocol import send_ack, send_error
from backend.core.state import connections
from backend.utils.logger import logger


async def handle_heartbeat(websocket, proto: dict):
    msg_id = proto.get("msg_id")
    ctx = connections[websocket]

    logger.info("收到业务心跳：user=%s", ctx.user_id or proto.get("from") or "unknown")

    if proto.get("need_ack"):
        if not isinstance(msg_id, str) or not msg_id:
            await send_error(websocket, "heartbeat 报文缺少合法 msg_id")
            return
        await send_ack(websocket, msg_id)