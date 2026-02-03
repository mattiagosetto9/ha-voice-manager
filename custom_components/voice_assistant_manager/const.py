"""Constants for Voice Assistant Manager integration."""
from typing import Final

DOMAIN: Final = "voice_assistant_manager"
VERSION: Final = "1.1.1"

# Storage
STORAGE_KEY: Final = "voice_assistant_manager"
STORAGE_VERSION: Final = 1  # Internal migration handles v1->v2 data structure

# Panel
PANEL_TITLE: Final = "Voice Assistant Manager"
PANEL_ICON: Final = "mdi:account-voice"
PANEL_NAME: Final = "voice-assistant-manager"

# Modes
MODE_LINKED: Final = "linked"
MODE_SEPARATE: Final = "separate"
VALID_MODES: Final = frozenset({MODE_LINKED, MODE_SEPARATE})

# Filter modes
FILTER_MODE_EXCLUDE: Final = "exclude"
FILTER_MODE_INCLUDE: Final = "include"
VALID_FILTER_MODES: Final = frozenset({FILTER_MODE_EXCLUDE, FILTER_MODE_INCLUDE})

# Assistant types
ASSISTANT_GOOGLE: Final = "google"
ASSISTANT_ALEXA: Final = "alexa"
ASSISTANT_HOMEKIT: Final = "homekit"
VALID_ASSISTANTS: Final = frozenset({ASSISTANT_GOOGLE, ASSISTANT_ALEXA, ASSISTANT_HOMEKIT})

# YAML output paths (relative to config dir)
GOOGLE_YAML_PATH: Final = "packages/generated_google_assistant.yaml"
ALEXA_YAML_PATH: Final = "packages/generated_alexa.yaml"

# Security: Allowed paths for YAML generation (must be within config dir)
ALLOWED_OUTPUT_DIRS: Final = frozenset({"packages"})

# Validation limits
MAX_ALIAS_LENGTH: Final = 128
MAX_ADVANCED_YAML_LENGTH: Final = 10000
MAX_ENTITY_ID_LENGTH: Final = 255
MAX_PATH_LENGTH: Final = 512
MAX_PROJECT_ID_LENGTH: Final = 128
MAX_PIN_LENGTH: Final = 32

# Bulk operation limits
MAX_BULK_ENTITIES: Final = 500

# Filter config structure
DEFAULT_FILTER_CONFIG: dict = {
    "filter_mode": FILTER_MODE_EXCLUDE,  # "exclude" or "include"
    "domains": [],      # domains to include/exclude
    "entities": [],     # individual entities
    "devices": [],      # devices
    "overrides": [],    # entity exceptions (re-include if excluded, exclude if included)
}

DEFAULT_GOOGLE_SETTINGS: dict = {
    "enabled": False,
    "project_id": "",
    "service_account_path": "",
    "report_state": True,
    "secure_devices_pin": "",
    "advanced_yaml": "",
}

DEFAULT_ALEXA_SETTINGS: dict = {
    "enabled": False,
    "advanced_yaml": "",
}

# HomeKit supported domains (for reference)
HOMEKIT_SUPPORTED_DOMAINS: Final = frozenset({
    "alarm_control_panel", "climate", "cover", "fan", "humidifier",
    "light", "lock", "switch", "water_heater", "binary_sensor",
    "button", "camera", "input_boolean", "lawn_mower", "scene",
    "script", "sensor", "valve",
})

DEFAULT_DATA: dict = {
    "mode": MODE_LINKED,
    # Linked mode data (new v2 structure)
    "filter_config": DEFAULT_FILTER_CONFIG.copy(),
    "aliases": {},
    # Separate mode data (new v2 structure)
    "google_filter_config": DEFAULT_FILTER_CONFIG.copy(),
    "google_aliases": {},
    "alexa_filter_config": DEFAULT_FILTER_CONFIG.copy(),
    "alexa_aliases": {},
    "homekit_filter_config": DEFAULT_FILTER_CONFIG.copy(),
    # HomeKit bridge config
    "homekit_entry_id": None,  # auto-detected or user-selected bridge entry
    # Settings
    "google_settings": DEFAULT_GOOGLE_SETTINGS.copy(),
    "alexa_settings": DEFAULT_ALEXA_SETTINGS.copy(),
    # Timestamps
    "last_generated": {
        "google": None,
        "alexa": None,
        "homekit": None,
    },
}
