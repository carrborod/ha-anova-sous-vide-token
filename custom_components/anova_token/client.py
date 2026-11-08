"""WebSocket client for Anova's official Wi-Fi API (Precision Cookers only)."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import aiohttp

from .const import (
    CMD_START,
    CMD_STOP,
    EVENT_STATE,
    EVENT_WIFI_LIST,
    RECONNECT_DELAY,
    SUPPORTED_ACCESSORIES,
    WS_URL,
)

_LOGGER = logging.getLogger(__name__)


class AnovaAuthError(Exception):
    """The token was rejected."""


class AnovaConnectionError(Exception):
    """Could not reach Anova or no cooker was found."""


@dataclass
class Cooker:
    """A Precision Cooker on the account."""

    cooker_id: str
    name: str
    device_type: str
    state: dict[str, Any] = field(default_factory=dict)


class AnovaTokenClient:
    """Keeps one WebSocket open to Anova and tracks the account's cookers."""

    def __init__(self, session: aiohttp.ClientSession, token: str) -> None:
        self._session = session
        self._token = token
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._task: asyncio.Task | None = None
        self._stopping = False
        self._listeners: list[Callable[[], None]] = []
        self.cookers: dict[str, Cooker] = {}
        self.connected = False
        self.devices_seen = asyncio.Event()

    @property
    def _url(self) -> str:
        return f"{WS_URL}?token={self._token}&supportedAccessories={SUPPORTED_ACCESSORIES}"

    def add_listener(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Register a callback for any change; returns a remover."""
        self._listeners.append(callback)

        def _remove() -> None:
            if callback in self._listeners:
                self._listeners.remove(callback)

        return _remove

    def _notify(self) -> None:
        for callback in list(self._listeners):
            try:
                callback()
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Listener failed")

    async def start(self) -> None:
        """Start the background connection loop."""
        self._stopping = False
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Close the connection and stop reconnecting."""
        self._stopping = True
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

    async def _run(self) -> None:
        while not self._stopping:
            try:
                await self._connect_and_listen()
            except AnovaAuthError:
                _LOGGER.error("Anova rejected the personal access token")
                self._set_connected(False)
                return
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Anova connection dropped: %s", err)
            self._set_connected(False)
            if not self._stopping:
                await asyncio.sleep(RECONNECT_DELAY)

    def _set_connected(self, value: bool) -> None:
        if self.connected != value:
            self.connected = value
            self._notify()

    async def _connect_and_listen(self) -> None:
        try:
            self._ws = await self._session.ws_connect(self._url, heartbeat=30)
        except aiohttp.WSServerHandshakeError as err:
            if err.status in (401, 403):
                raise AnovaAuthError from err
            raise
        self._set_connected(True)
        _LOGGER.debug("Connected to Anova")
        async for msg in self._ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                self._handle(msg.data)
            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                break

    def _handle(self, raw: str) -> None:
        try:
            data = json.loads(raw)
        except ValueError:
            return
        command = data.get("command", "")
        payload = data.get("payload")
        _LOGGER.debug("Anova message %s: %s", command, payload)

        if command == EVENT_WIFI_LIST and isinstance(payload, list):
            for item in payload:
                cooker_id = item.get("cookerId")
                if not cooker_id:
                    continue
                existing = self.cookers.get(cooker_id)
                if existing:
                    existing.name = item.get("name", existing.name)
                    existing.device_type = item.get("type", existing.device_type)
                else:
                    self.cookers[cooker_id] = Cooker(
                        cooker_id=cooker_id,
                        name=item.get("name") or "Anova Precision Cooker",
                        device_type=item.get("type", "unknown"),
                    )
            self.devices_seen.set()
            self._notify()
        elif command == EVENT_STATE and isinstance(payload, dict):
            cooker_id = payload.get("cookerId")
            cooker = self.cookers.get(cooker_id) if cooker_id else None
            if cooker is None and len(self.cookers) == 1:
                cooker = next(iter(self.cookers.values()))
            if cooker is not None:
                cooker.state = payload
                self._notify()
        elif command.startswith("RESPONSE"):
            _LOGGER.debug("Anova response: %s", data)

    async def _send(self, message: dict[str, Any]) -> None:
        if self._ws is None or self._ws.closed:
            raise AnovaConnectionError("Not connected to Anova")
        await self._ws.send_str(json.dumps(message))

    async def start_cook(self, cooker_id: str, temp_c: float, timer_seconds: int) -> None:
        """Start a sous vide cook. Temperature is always sent in Celsius."""
        cooker = self.cookers[cooker_id]
        await self._send(
            {
                "command": CMD_START,
                "requestId": str(uuid.uuid4()),
                "payload": {
                    "cookerId": cooker_id,
                    "type": cooker.device_type,
                    "targetTemperature": round(temp_c, 1),
                    "unit": "C",
                    "timer": int(timer_seconds),
                },
            }
        )

    async def stop_cook(self, cooker_id: str) -> None:
        """Stop the current cook."""
        cooker = self.cookers[cooker_id]
        await self._send(
            {
                "command": CMD_STOP,
                "requestId": str(uuid.uuid4()),
                "payload": {"cookerId": cooker_id, "type": cooker.device_type},
            }
        )


async def validate_token(session: aiohttp.ClientSession, token: str, timeout: float) -> dict[str, Cooker]:
    """Connect once and return the cookers on the account."""
    client = AnovaTokenClient(session, token)
    try:
        ws = await session.ws_connect(client._url)  # noqa: SLF001
    except aiohttp.WSServerHandshakeError as err:
        if err.status in (401, 403):
            raise AnovaAuthError from err
        raise AnovaConnectionError(str(err)) from err
    except aiohttp.ClientError as err:
        raise AnovaConnectionError(str(err)) from err
    try:
        async with asyncio.timeout(timeout):
            async for msg in ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    break
                client._handle(msg.data)  # noqa: SLF001
                if client.devices_seen.is_set():
                    break
    except TimeoutError:
        pass
    finally:
        await ws.close()
    if not client.cookers:
        raise AnovaConnectionError("No Precision Cooker found on this account")
    return client.cookers
