import asyncio
import json
import threading
from time import time

from backend.config import NODE_ID, REDIS_KEY_PREFIX
from backend.core.local_delivery_service import (
    deliver_private_message_online_only_locally,
    deliver_room_message_online_only_locally,
)
from backend.core.redis_client import redis_client
from backend.core.state import processed_message_keys

PUBSUB_CHANNEL = f"{REDIS_KEY_PREFIX}:messages"

_listener_thread = None


def publish_distributed_message(message: dict) -> None:
    redis_client.publish(PUBSUB_CHANNEL, json.dumps(message, ensure_ascii=False))


def start_pubsub_listener(loop: asyncio.AbstractEventLoop) -> None:
    global _listener_thread

    if _listener_thread is not None and _listener_thread.is_alive():
        return

    _listener_thread = threading.Thread(
        target=_pubsub_worker,
        args=(loop,),
        daemon=True,
        name=f"pubsub-listener-{NODE_ID}",
    )
    _listener_thread.start()


def _pubsub_worker(loop: asyncio.AbstractEventLoop) -> None:
    pubsub = redis_client.pubsub(ignore_subscribe_messages=True)
    pubsub.subscribe(PUBSUB_CHANNEL)

    for item in pubsub.listen():
        if item.get("type") != "message":
            continue

        raw_data = item.get("data")
        if not isinstance(raw_data, str):
            continue

        try:
            message = json.loads(raw_data)
        except json.JSONDecodeError:
            continue

        if not isinstance(message, dict):
            continue

        source_node_id = message.get("source_node_id")
        if source_node_id == NODE_ID:
            continue

        asyncio.run_coroutine_threadsafe(
            handle_distributed_message(message),
            loop,
        )


async def handle_distributed_message(message: dict) -> None:
    msg_id = message.get("msg_id")
    msg_type = message.get("msg_type")
    conversation_id = message.get("conversation_id")
    from_user_id = message.get("from_user_id")
    payload = message.get("payload", {})

    if not isinstance(msg_id, str) or not msg_id:
        return
    if not isinstance(msg_type, str) or not msg_type:
        return
    if not isinstance(conversation_id, str) or not conversation_id:
        return
    if not isinstance(from_user_id, str) or not from_user_id:
        return
    if not isinstance(payload, dict):
        return

    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        return

    dedupe_key = f"{from_user_id}:{msg_id}"
    if dedupe_key in processed_message_keys:
        return

    if msg_type == "room_chat":
        await deliver_room_message_online_only_locally(
            msg_id=msg_id,
            conversation_id=conversation_id,
            from_user_id=from_user_id,
            text=text.strip(),
        )
    elif msg_type == "private_chat":
        to_user_id = message.get("to_user_id")
        if not isinstance(to_user_id, str) or not to_user_id:
            return

        await deliver_private_message_online_only_locally(
            msg_id=msg_id,
            conversation_id=conversation_id,
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            text=text.strip(),
        )
    else:
        return

    processed_message_keys[dedupe_key] = int(time())