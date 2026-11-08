"""Constants for the Anova Sous Vide (Token) integration."""

DOMAIN = "anova_token"

CONF_TOKEN = "token"

WS_URL = "wss://devices.anovaculinary.io"
SUPPORTED_ACCESSORIES = "APC"

EVENT_WIFI_LIST = "EVENT_APC_WIFI_LIST"
EVENT_STATE = "EVENT_APC_STATE"

CMD_START = "CMD_APC_START"
CMD_STOP = "CMD_APC_STOP"

# Anova's own example client caps sous vide at 95 °C.
MIN_TEMP_C = 0.0
MAX_TEMP_C = 95.0
DEFAULT_TEMP_C = 57.0
DEFAULT_TIMER_MIN = 60

RECONNECT_DELAY = 10
DISCOVERY_TIMEOUT = 15

SERVICE_START_COOK = "start_cook"
SERVICE_STOP_COOK = "stop_cook"
