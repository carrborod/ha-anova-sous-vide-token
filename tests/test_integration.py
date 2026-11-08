"""End-to-end test against a fake Anova WebSocket server."""

import asyncio
import json

import pytest
from aiohttp import web

from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM

from custom_components.anova_token import client as client_mod
from custom_components.anova_token.const import DOMAIN

COOKER = {"cookerId": "abc123", "name": "Anova Precision Cooker", "pairedAt": "x", "type": "a6"}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations, socket_enabled):
    yield


@pytest.fixture
async def fake_anova(aiohttp_server, monkeypatch):
    received: list[dict] = []
    tokens: list[str] = []

    async def handler(request):
        tokens.append(request.query.get("token"))
        assert request.query.get("supportedAccessories") == "APC"
        if request.query.get("token") == "anova-bad":
            return web.Response(status=401)
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await ws.send_str(json.dumps({"command": "EVENT_APC_WIFI_LIST", "payload": [COOKER]}))
        await ws.send_str(
            json.dumps(
                {
                    "command": "EVENT_APC_STATE",
                    "payload": {"cookerId": "abc123", "state": {"state": {"mode": "idle"}}},
                }
            )
        )
        async for msg in ws:
            data = json.loads(msg.data)
            received.append(data)
            await ws.send_str(json.dumps({"command": "RESPONSE", "requestId": data["requestId"]}))
        return ws

    app = web.Application()
    app.router.add_get("/", handler)
    server = await aiohttp_server(app)
    monkeypatch.setattr(client_mod, "WS_URL", f"ws://127.0.0.1:{server.port}/")
    return received, tokens


async def _setup(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == "form"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOKEN: " anova-good "}
    )
    assert result["type"] == "create_entry", result
    assert result["title"] == "Anova control (Anova Precision Cooker)"
    await hass.async_block_till_done()


async def test_bad_token(hass: HomeAssistant, fake_anova):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_TOKEN: "anova-bad"})
    assert result["errors"] == {"base": "invalid_auth"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_TOKEN: "nope"})
    assert result["errors"] == {"base": "bad_format"}


async def test_start_stop_fahrenheit(hass: HomeAssistant, fake_anova):
    received, tokens = fake_anova
    hass.config.units = US_CUSTOMARY_SYSTEM
    await _setup(hass)
    assert tokens[-1] == "anova-good"

    states = {s.entity_id: s for s in hass.states.async_all() if "anova" in s.entity_id}
    print(sorted(states))
    temp_id = next(e for e in states if e.startswith("number.") and "temperature" in e)
    timer_id = next(e for e in states if e.startswith("number.") and "timer" in e)
    start_id = next(e for e in states if e.startswith("button.") and "start" in e)
    stop_id = next(e for e in states if e.startswith("button.") and "stop" in e)
    conn_id = next(e for e in states if e.startswith("binary_sensor."))
    raw_id = next(e for e in states if e.startswith("sensor."))
    assert states[conn_id].state == "on"
    assert hass.states.get(raw_id).state == "idle"
    assert states[temp_id].attributes["unit_of_measurement"] == "°F"

    await hass.services.async_call("number", "set_value", {"entity_id": temp_id, "value": 135}, blocking=True)
    await hass.services.async_call("number", "set_value", {"entity_id": timer_id, "value": 90}, blocking=True)
    await hass.services.async_call("button", "press", {"entity_id": start_id}, blocking=True)
    await asyncio.sleep(0.2)
    start = received[-1]
    assert start["command"] == "CMD_APC_START"
    assert start["payload"] == {
        "cookerId": "abc123",
        "type": "a6",
        "targetTemperature": 57.2,
        "unit": "C",
        "timer": 5400,
    }

    await hass.services.async_call("button", "press", {"entity_id": stop_id}, blocking=True)
    await asyncio.sleep(0.2)
    assert received[-1]["command"] == "CMD_APC_STOP"
    assert received[-1]["payload"] == {"cookerId": "abc123", "type": "a6"}

    await hass.services.async_call(
        DOMAIN, "start_cook", {"temperature": 60, "unit": "C", "minutes": 30}, blocking=True
    )
    await asyncio.sleep(0.2)
    assert received[-1]["payload"]["targetTemperature"] == 60.0
    assert received[-1]["payload"]["timer"] == 1800

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_start_celsius(hass: HomeAssistant, fake_anova):
    received, _ = fake_anova
    await _setup(hass)
    temp_id = next(s.entity_id for s in hass.states.async_all() if s.entity_id.startswith("number.") and "temperature" in s.entity_id)
    start_id = next(s.entity_id for s in hass.states.async_all() if s.entity_id.startswith("button.") and "start" in s.entity_id)
    await hass.services.async_call("number", "set_value", {"entity_id": temp_id, "value": 63.5}, blocking=True)
    await hass.services.async_call("button", "press", {"entity_id": start_id}, blocking=True)
    await asyncio.sleep(0.2)
    assert received[-1]["payload"]["targetTemperature"] == 63.5
    assert received[-1]["payload"]["timer"] == 3600
