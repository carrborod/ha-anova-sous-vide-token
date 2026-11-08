"""Target temperature and timer settings used by the Start cook button."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberMode, RestoreNumber
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEFAULT_TEMP_C, DEFAULT_TIMER_MIN, MAX_TEMP_C, MIN_TEMP_C
from .entity import AnovaTokenEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    client = entry.runtime_data
    entities = []
    for cooker_id in client.cookers:
        entities.append(CookTemperature(client, cooker_id))
        entities.append(CookTimer(client, cooker_id))
    async_add_entities(entities)


class _Setting(AnovaTokenEntity, RestoreNumber):
    """A setting kept in Home Assistant (the cooker is only told on Start)."""

    _attr_mode = NumberMode.BOX
    _default: float

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        self._attr_native_value = (
            last.native_value if last and last.native_value is not None else self._default
        )

    @property
    def available(self) -> bool:
        return True

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        self.async_write_ha_state()


class CookTemperature(_Setting):
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = MIN_TEMP_C
    _attr_native_max_value = MAX_TEMP_C
    _attr_native_step = 0.5
    _default = DEFAULT_TEMP_C

    def __init__(self, client, cooker_id) -> None:
        super().__init__(client, cooker_id, "cook_temperature")


class CookTimer(_Setting):
    _attr_device_class = NumberDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_native_min_value = 1
    _attr_native_max_value = 6000
    _attr_native_step = 1
    _default = DEFAULT_TIMER_MIN

    def __init__(self, client, cooker_id) -> None:
        super().__init__(client, cooker_id, "cook_timer")
