"""Anova Sous Vide (Token): start/stop control for Anova Precision Cookers."""

from __future__ import annotations

import asyncio
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import AnovaConnectionError, AnovaTokenClient
from .const import (
    CONF_TOKEN,
    DISCOVERY_TIMEOUT,
    DOMAIN,
    MAX_TEMP_C,
    MIN_TEMP_C,
    SERVICE_START_COOK,
    SERVICE_STOP_COOK,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.NUMBER, Platform.SENSOR]

START_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): cv.string,
        vol.Required("temperature"): vol.Coerce(float),
        vol.Optional("unit", default="F"): vol.In(["C", "F"]),
        vol.Required("minutes"): vol.All(vol.Coerce(int), vol.Range(min=1, max=6000)),
    }
)
STOP_SCHEMA = vol.Schema({vol.Optional("device_id"): cv.string})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry."""
    client = AnovaTokenClient(async_get_clientsession(hass), entry.data[CONF_TOKEN])
    await client.start()
    try:
        async with asyncio.timeout(DISCOVERY_TIMEOUT):
            await client.devices_seen.wait()
    except TimeoutError:
        _LOGGER.warning("Anova did not list any cookers yet; entities will appear once it does")

    entry.runtime_data = client
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.stop()
    return unloaded


def _resolve(hass: HomeAssistant, device_id: str | None) -> tuple[AnovaTokenClient, str]:
    """Find the client and cooker id for a service call."""
    entries = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.state is ConfigEntryState.LOADED
    ]
    if device_id:
        device = dr.async_get(hass).async_get(device_id)
        if device is None:
            raise HomeAssistantError("Unknown device")
        for domain, ident in device.identifiers:
            if domain == DOMAIN:
                for entry in entries:
                    if ident in entry.runtime_data.cookers:
                        return entry.runtime_data, ident
        raise HomeAssistantError("That device is not an Anova cooker from this integration")
    for entry in entries:
        if entry.runtime_data.cookers:
            return entry.runtime_data, next(iter(entry.runtime_data.cookers))
    raise HomeAssistantError("No Anova cooker available")


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_START_COOK):
        return

    async def _start(call: ServiceCall) -> None:
        client, cooker_id = _resolve(hass, call.data.get("device_id"))
        temp = call.data["temperature"]
        temp_c = (temp - 32) * 5 / 9 if call.data["unit"] == "F" else temp
        if not MIN_TEMP_C <= temp_c <= MAX_TEMP_C:
            raise HomeAssistantError(f"Temperature must be between {MIN_TEMP_C} and {MAX_TEMP_C} °C")
        try:
            await client.start_cook(cooker_id, temp_c, call.data["minutes"] * 60)
        except AnovaConnectionError as err:
            raise HomeAssistantError(str(err)) from err

    async def _stop(call: ServiceCall) -> None:
        client, cooker_id = _resolve(hass, call.data.get("device_id"))
        try:
            await client.stop_cook(cooker_id)
        except AnovaConnectionError as err:
            raise HomeAssistantError(str(err)) from err

    hass.services.async_register(DOMAIN, SERVICE_START_COOK, _start, schema=START_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_STOP_COOK, _stop, schema=STOP_SCHEMA)
