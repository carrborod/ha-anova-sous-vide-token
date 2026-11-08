"""Config flow: paste an Anova personal access token."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import AnovaAuthError, AnovaConnectionError, validate_token
from .const import CONF_TOKEN, DISCOVERY_TIMEOUT, DOMAIN

_LOGGER = logging.getLogger(__name__)


class AnovaTokenConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            if not token.startswith("anova-"):
                errors["base"] = "bad_format"
            else:
                try:
                    cookers = await validate_token(
                        async_get_clientsession(self.hass), token, DISCOVERY_TIMEOUT
                    )
                except AnovaAuthError:
                    errors["base"] = "invalid_auth"
                except AnovaConnectionError:
                    errors["base"] = "no_cookers"
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("Unexpected error validating Anova token")
                    errors["base"] = "unknown"
                else:
                    await self.async_set_unique_id(sorted(cookers)[0])
                    self._abort_if_unique_id_configured()
                    names = ", ".join(c.name for c in cookers.values())
                    return self.async_create_entry(
                        title=f"Anova control ({names})", data={CONF_TOKEN: token}
                    )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_TOKEN): str}),
            errors=errors,
        )
