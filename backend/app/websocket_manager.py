import asyncio
import json

from fastapi import WebSocket

SEND_TIMEOUT_SECONDS = 2.0


class ConnectionManager:
    def __init__(self):
        self.connections = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.connections:
            self.connections.remove(websocket)

    async def broadcast(self, payload: dict):
        if not self.connections:
            return

        message = json.dumps(payload, default=str)
        receivers = list(self.connections)

        results = await asyncio.gather(
            *(self.send(websocket, message) for websocket in receivers),
            return_exceptions=True
        )

        for websocket, result in zip(receivers, results):
            if result is not True:
                self.disconnect(websocket)

    async def send(self, websocket: WebSocket, message: str) -> bool:
        try:
            await asyncio.wait_for(
                websocket.send_text(message), timeout=SEND_TIMEOUT_SECONDS
            )
            return True

        except Exception:
            return False


manager = ConnectionManager()
