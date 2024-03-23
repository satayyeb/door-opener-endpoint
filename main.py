import os
from datetime import datetime
from typing import Annotated

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Header, HTTPException
from fastapi.responses import HTMLResponse

load_dotenv('local.env')
API_AUTHORIZATION_TOKEN_LIST = [token.strip() for token in os.environ.get('API_AUTHORIZATION_TOKEN_LIST').split(',')]
ESP_AUTHORIZATION_TOKEN = os.environ.get('ESP_AUTHORIZATION_TOKEN')


class WebSocketConnectionManager:
    def __init__(self):
        self.active_connection: WebSocket | None = None
        self.last_change: datetime | None = None

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connection = websocket
        self.last_change = datetime.now()
        self.log_in_file(True)

    def disconnect(self, websocket: WebSocket):
        self.active_connection = None
        self.last_change = datetime.now()
        self.log_in_file(False)

    def log_in_file(self, is_connection_event: bool):
        with open('data/log.txt', 'a+') as f:
            f.write(('new , {}\n' if is_connection_event else 'loss, {}\n').format(self.last_change))

    async def send_open_door_command(self):
        if not self.active_connection:
            raise HTTPException(503, 'No active connection.')
        return await self.active_connection.send_text('open-door')


websocket_manager = WebSocketConnectionManager()

app = FastAPI()


@app.get("/", response_class=HTMLResponse)
async def get():
    home_page = """
        <!DOCTYPE html>
        <html>
            <head>
                <title>Door opener endpoint</title>
            </head>
            <body>
                <h1>Door opener endpoint</h1>
                <h3>status: {status}</h3>
            </body>
        </html>
        """
    return HTMLResponse(
        home_page.format(status='connected ✅' if websocket_manager.active_connection else 'disconnected ❌')
    )


@app.get("/status")
async def get_status():
    return websocket_manager.active_connection is not None


@app.post("/open")
async def open_door(
        authorization: Annotated[str | None, Header()] = None
):
    if authorization not in API_AUTHORIZATION_TOKEN_LIST:
        raise HTTPException(status_code=401, detail='Unauthorized request.')
    await websocket_manager.send_open_door_command()
    return 'The door opened successfully.'


@app.websocket("/ws")
async def websocket_endpoint(
        websocket: WebSocket,
        authorization: Annotated[str | None, Header()] = None
):
    if authorization != ESP_AUTHORIZATION_TOKEN:
        return await websocket.close(1008, 'Unauthorized request.')
    if websocket_manager.active_connection:
        return await websocket.close(1008, 'Another ESP is connected.')
    await websocket_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"I've received '{data}'.")
    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket)
