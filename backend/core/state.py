import asyncio
from dataclasses import dataclass, field
from time import time
from typing import Any


@dataclass
class ConnectionContext:
    websocket: Any
    user_id: str | None = None
    is_authenticated: bool = False
    connected_at: int = field(default_factory=lambda: int(time()))
    last_pong: int = field(default_factory=lambda: int(time()))
    heartbeat_task: asyncio.Task | None = None


connections: dict[Any, ConnectionContext] = {}

server = None