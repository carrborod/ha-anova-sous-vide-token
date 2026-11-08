"""Start and stop buttons."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import AnovaConnectionError
from .const import DEFAULT_TEMP_C, DEFAULT_TIMER_MIN, DOMAIN
from .entity import AnovaTokenEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    client = entry.runtime_data
    entities = []
    for cooker_id in client.cookers:
        entities.append(StartButton(client, cooker_id))
        entities.append(StopButton(client, cooker_id))
    async_add_entities(entities)


class StartButton(AnovaTokenEntity, ButtonEntity):
    """Starts a cook using the Cook temperature and Cook timer settings."""

    _attr_icon = "mdi:play"

    def __init__(self, client, cooker_id) -> None:
        super().__init__(client, cooker_id, "start_cook")

    def _setting(self, key: str, default: float, default_unit: str) -> tuple[float, str]:
        """Read a number entity's displayed value and unit."""
        registry = er.async_get(self.hass)
        entity_id = registry.async_get_entity_id("number", DOMAIN, f"{self.cooker_id}_{key}")
        state = self.hass.states.get(entity_id) if entity_id else None
        if state is None or state.state in ("unknown", "unavailable"):
            return default, default_unit
        return float(state.state), state.attributes.get("unit_of_measurement", default_unit)

    async def async_press(self) -> None:
        temp_value, temp_unit = self._setting("cook_temperature", DEFAULT_TEMP_C, "°C")
        timer_min, _ = self._setting("cook_timer", DEFAULT_TIMER_MIN, "min")
        temp_c = (temp_value - 32) * 5 / 9 if temp_unit == "°F" else temp_value
        try:
            await self.client.start_cook(self.cooker_id, temp_c, int(timer_min * 60))
        except AnovaConnectionError as err:
            raise HomeAssistantError(str(err)) from err


class StopButton(AnovaTokenEntity, ButtonEntity):
    """Stops the current cook."""

    _attr_icon = "mdi:stop"

    def __init__(self, client, cooker_id) -> None:
        super().__init__(client, cooker_id, "stop_cook")

    async def async_press(self) -> None:
        try:
            await self.client.stop_cook(self.cooker_id)
        except AnovaConnectionError as err:
            raise HomeAssistantError(str(err)) from err
