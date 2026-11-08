"""Raw state from Anova's API, kept as a diagnostic.

Anova does not document the EVENT_APC_STATE payload, so this sensor exposes it
as attributes rather than guessing at fields. Day-to-day temperatures come from
Home Assistant's built-in Anova integration.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import AnovaTokenEntity

_STATE_KEYS = ("state", "status", "mode", "jobStatus")


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    client = entry.runtime_data
    async_add_entities(RawState(client, cid) for cid in client.cookers)


def _flatten(data: Any, prefix: str = "", out: dict[str, Any] | None = None) -> dict[str, Any]:
    out = {} if out is None else out
    if isinstance(data, dict):
        for key, value in data.items():
            _flatten(value, f"{prefix}{key}." if isinstance(value, dict) else f"{prefix}{key}", out)
    else:
        out[prefix.rstrip(".")] = data
    return out


class RawState(AnovaTokenEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:code-json"

    def __init__(self, client, cooker_id) -> None:
        super().__init__(client, cooker_id, "api_state")

    @property
    def _payload(self) -> dict[str, Any]:
        return self.client.cookers[self.cooker_id].state

    @property
    def native_value(self) -> str | None:
        flat = _flatten(self._payload)
        for key in _STATE_KEYS:
            for flat_key, value in flat.items():
                if flat_key.split(".")[-1] == key and isinstance(value, (str, int, float)):
                    return str(value)[:255]
        return "received" if self._payload else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        flat = _flatten(self._payload)
        return {k: v for k, v in list(flat.items())[:60] if isinstance(v, (str, int, float, bool))}
