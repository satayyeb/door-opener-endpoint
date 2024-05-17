import os
from asyncio import sleep
from datetime import datetime
from textwrap import dedent
from typing import Annotated

import requests
import sentry_sdk
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Header, HTTPException
from fastapi.responses import HTMLResponse

load_dotenv('local.env')
API_AUTHORIZATION_TOKEN_LIST = [token.strip() for token in os.environ.get('API_AUTHORIZATION_TOKEN_LIST').split(',')]
ESP_AUTHORIZATION_TOKEN = os.environ.get('ESP_AUTHORIZATION_TOKEN')
UPDATE_AUTHORIZATION_TOKEN = os.environ.get('UPDATE_AUTHORIZATION_TOKEN')
SENTRY_DSN = os.environ.get('SENTRY_DSN')


class WebSocketConnectionManager:
    LOG_FILE_PATH = 'data/log.txt'
    FIRMWARE_FILE_PATH = 'data/firmware.bin'

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
        with open(self.LOG_FILE_PATH, 'a+') as f:
            f.write(('new , {}\n' if is_connection_event else 'loss, {}\n').format(self.last_change))
        # Delete the log file, if it exceeds 100 MB:
        if os.path.getsize(self.LOG_FILE_PATH) > 100 * 1024 * 1024:
            os.remove(self.LOG_FILE_PATH)

    async def send_open_door_command(self):
        if not self.active_connection:
            raise HTTPException(503, 'No active connection.')
        return await self.active_connection.send_json({'command': 'open-door', 'message': 'Please open the door.'})

    async def send_update_firmware_command(self):
        if not self.active_connection:
            raise HTTPException(503, 'No active connection.')
        firmware_size = os.path.getsize(self.FIRMWARE_FILE_PATH)
        await self.active_connection.send_json({'command': 'update', 'size': firmware_size})
        # response = await self.active_connection.receive_json()
        # if not response['success']:
        #     raise HTTPException(400, response['message'])

        with open(self.FIRMWARE_FILE_PATH, "rb") as binary_file:
            while True:
                chunk = binary_file.read(4096)
                if not chunk:
                    break
                try:
                    await self.active_connection.send_bytes(chunk)
                except Exception:
                    raise HTTPException(500, 'Error in send firmware.')
                await sleep(0.2)


websocket_manager = WebSocketConnectionManager()

sentry_sdk.init(
    dsn=SENTRY_DSN,
    traces_sample_rate=1.0,
)

app = FastAPI()


@app.get("/", response_class=HTMLResponse)
async def get():
    home_page = dedent("""
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
    """)
    return HTMLResponse(
        home_page.format(status='connected ✅' if websocket_manager.active_connection else 'disconnected ❌')
    )


@app.get("/status")
async def get_status():
    return HTMLResponse(str(websocket_manager.active_connection is not None))


@app.post("/update")
async def open_door(
        authorization: Annotated[str | None, Header()] = None
):
    if authorization != UPDATE_AUTHORIZATION_TOKEN:
        raise HTTPException(status_code=401, detail='Unauthorized request.')
    await websocket_manager.send_update_firmware_command()
    return 'OK'


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
            await websocket.send_json({'command': 'server-echo', 'message': f"I've received '{data}'."})
    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket)


@app.exception_handler(404)
async def not_found_exception_handler(request, exc):
    custom_404_page = dedent('''
        <!doctype html>
        <html lang="en">
        <head>
            <title>Not Found</title>
        </head>
        <body>
        <h1>Not Found</h1><p>The requested resource was not found on this server.</p>
        </body>
        </html>
    ''')
    return HTMLResponse(custom_404_page)
