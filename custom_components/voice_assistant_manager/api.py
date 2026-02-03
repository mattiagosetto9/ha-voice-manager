"""WebSocket API for Voice Assistant Manager integration.

This module provides all WebSocket command handlers for the Voice Assistant Manager
frontend panel to communicate with the backend.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    area_registry as ar,
)
from homeassistant.helpers import (
    device_registry as dr,
)
from homeassistant.helpers import (
    entity_registry as er,
)

from .const import (
    ASSISTANT_ALEXA,
    ASSISTANT_GOOGLE,
    ASSISTANT_HOMEKIT,
    DOMAIN,
    FILTER_MODE_EXCLUDE,
    FILTER_MODE_INCLUDE,
    HOMEKIT_SUPPORTED_DOMAINS,
    MAX_BULK_ENTITIES,
    MODE_LINKED,
    MODE_SEPARATE,
)
from .exceptions import HomeKitError, ValidationError, VoiceManagerError
from .homekit_manager import HomeKitManager
from .validators import (
    validate_alexa_settings,
    validate_alias,
    validate_assistant,
    validate_domains,
    validate_entity_id,
    validate_entity_ids,
    validate_filter_config,
    validate_filter_mode,
    validate_google_settings,
    validate_mode,
)
from .yaml_generator import YAMLGenerator

_LOGGER = logging.getLogger(__name__)


def async_register_websocket_api(hass: HomeAssistant) -> None:
    """Register all WebSocket API commands.

    Args:
        hass: Home Assistant instance.
    """
    # Core endpoints
    websocket_api.async_register_command(hass, websocket_get_state)
    websocket_api.async_register_command(hass, websocket_set_mode)

    # Filter config endpoints
    websocket_api.async_register_command(hass, websocket_set_filter_mode)
    websocket_api.async_register_command(hass, websocket_set_filter_config)
    websocket_api.async_register_command(hass, websocket_set_domains)
    websocket_api.async_register_command(hass, websocket_toggle_override)

    # Alias endpoints
    websocket_api.async_register_command(hass, websocket_set_alias)
    websocket_api.async_register_command(hass, websocket_bulk_update)

    # Settings endpoints
    websocket_api.async_register_command(hass, websocket_set_settings)
    websocket_api.async_register_command(hass, websocket_save_all)

    # YAML generation endpoints
    websocket_api.async_register_command(hass, websocket_preview_yaml)
    websocket_api.async_register_command(hass, websocket_write_files)

    # HomeKit endpoints
    websocket_api.async_register_command(hass, websocket_get_homekit_bridges)
    websocket_api.async_register_command(hass, websocket_set_homekit_bridge)
    websocket_api.async_register_command(hass, websocket_sync_homekit)
    websocket_api.async_register_command(hass, websocket_import_homekit)

    # System endpoints
    websocket_api.async_register_command(hass, websocket_check_config)
    websocket_api.async_register_command(hass, websocket_restart)

    _LOGGER.debug("Voice Assistant Manager WebSocket API registered")


def _get_storage(hass: HomeAssistant):
    """Get the storage instance."""
    return hass.data[DOMAIN]["storage"]


def _get_homekit_manager(hass: HomeAssistant) -> HomeKitManager:
    """Get or create the HomeKit manager instance."""
    if "homekit_manager" not in hass.data[DOMAIN]:
        storage = _get_storage(hass)
        hass.data[DOMAIN]["homekit_manager"] = HomeKitManager(hass, storage)
    return hass.data[DOMAIN]["homekit_manager"]


def _get_entities_data(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Get all entities with their device and area information."""
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    area_reg = ar.async_get(hass)

    entities = []

    for entity in ent_reg.entities.values():
        if entity.disabled:
            continue

        device_name = None
        device_area_id = None
        if entity.device_id:
            device = dev_reg.async_get(entity.device_id)
            if device:
                device_name = device.name_by_user or device.name
                device_area_id = device.area_id

        area_id = entity.area_id or device_area_id
        area_name = None
        if area_id:
            area = area_reg.async_get_area(area_id)
            if area:
                area_name = area.name

        state = hass.states.get(entity.entity_id)
        friendly_name = None
        if state:
            friendly_name = state.attributes.get("friendly_name")

        if not friendly_name:
            friendly_name = entity.name or entity.original_name or entity.entity_id

        domain = entity.entity_id.split(".")[0]

        entities.append(
            {
                "entity_id": entity.entity_id,
                "name": friendly_name,
                "domain": domain,
                "device_id": entity.device_id,
                "device_name": device_name,
                "area_id": area_id,
                "area_name": area_name,
                "platform": entity.platform,
            }
        )

    return entities


def _get_devices_data(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Get all devices."""
    dev_reg = dr.async_get(hass)
    area_reg = ar.async_get(hass)

    devices = []
    for device in dev_reg.devices.values():
        if device.disabled:
            continue

        area_name = None
        if device.area_id:
            area = area_reg.async_get_area(device.area_id)
            if area:
                area_name = area.name

        devices.append(
            {
                "id": device.id,
                "name": device.name_by_user or device.name,
                "area_id": device.area_id,
                "area_name": area_name,
                "manufacturer": device.manufacturer,
                "model": device.model,
            }
        )

    return devices


def _get_areas_data(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Get all areas."""
    area_reg = ar.async_get(hass)
    return [
        {"id": area.id, "name": area.name}
        for area in area_reg.async_list_areas()
    ]


def _get_domains(hass: HomeAssistant) -> list[str]:
    """Get all unique domains from entities."""
    ent_reg = er.async_get(hass)
    domains = set()
    for entity in ent_reg.entities.values():
        if not entity.disabled:
            domain = entity.entity_id.split(".")[0]
            domains.add(domain)
    return sorted(domains)


# ============ Core Endpoints ============

@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "voice_assistant_manager/get_state",
    }
)
@websocket_api.async_response
async def websocket_get_state(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Get full state including entities, devices, areas, and settings."""
    try:
        storage = _get_storage(hass)
        hk_manager = _get_homekit_manager(hass)

        state = storage.get_full_state()
        state["entities"] = _get_entities_data(hass)
        state["devices"] = _get_devices_data(hass)
        state["areas"] = _get_areas_data(hass)
        state["domains"] = _get_domains(hass)

        # Add HomeKit bridges info
        state["homekit_bridges"] = hk_manager.get_homekit_bridges()
        state["homekit_supported_domains"] = sorted(HOMEKIT_SUPPORTED_DOMAINS)

        connection.send_result(msg["id"], state)
    except Exception as err:
        _LOGGER.error("Failed to get state: %s", err)
        connection.send_error(msg["id"], "state_error", str(err))


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "voice_assistant_manager/set_mode",
        vol.Required("mode"): vol.In([MODE_LINKED, MODE_SEPARATE]),
    }
)
@websocket_api.async_response
async def websocket_set_mode(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Set the mode (linked or separate)."""
    try:
        validated_mode = validate_mode(msg["mode"])
        storage = _get_storage(hass)
        await storage.async_set_mode(validated_mode)
        connection.send_result(msg["id"], {"success": True, "mode": validated_mode})
    except ValidationError as err:
        connection.send_error(msg["id"], "validation_error", str(err))
    except Exception as err:
        _LOGGER.error("Failed to set mode: %s", err)
        connection.send_error(msg["id"], "mode_error", str(err))


# ============ Filter Config Endpoints (v2) ============

@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "voice_assistant_manager/set_filter_mode",
        vol.Required("filter_mode"): vol.In([FILTER_MODE_EXCLUDE, FILTER_MODE_INCLUDE]),
        vol.Optional("assistant"): vol.In([ASSISTANT_GOOGLE, ASSISTANT_ALEXA, ASSISTANT_HOMEKIT]),
    }
)
@websocket_api.async_response
async def websocket_set_filter_mode(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Set the filter mode (include or exclude) for an assistant."""
    try:
        filter_mode = validate_filter_mode(msg["filter_mode"])
        assistant = validate_assistant(msg.get("assistant"))

        storage = _get_storage(hass)
        await storage.async_set_filter_mode(filter_mode, assistant)

        connection.send_result(msg["id"], {"success": True, "filter_mode": filter_mode})
    except ValidationError as err:
        connection.send_error(msg["id"], "validation_error", str(err))
    except Exception as err:
        _LOGGER.error("Failed to set filter mode: %s", err)
        connection.send_error(msg["id"], "filter_mode_error", str(err))


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "voice_assistant_manager/set_filter_config",
        vol.Required("filter_config"): {
            vol.Optional("filter_mode"): vol.In([FILTER_MODE_EXCLUDE, FILTER_MODE_INCLUDE]),
            vol.Optional("domains"): [str],
            vol.Optional("entities"): [str],
            vol.Optional("devices"): [str],
            vol.Optional("overrides"): [str],
        },
        vol.Optional("assistant"): vol.In([ASSISTANT_GOOGLE, ASSISTANT_ALEXA, ASSISTANT_HOMEKIT]),
    }
)
@websocket_api.async_response
async def websocket_set_filter_config(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Set the complete filter configuration for an assistant."""
    try:
        assistant = validate_assistant(msg.get("assistant"))
        storage = _get_storage(hass)

        # Get current config and merge with new values
        current = storage.get_filter_config(assistant)
        new_config = msg["filter_config"]

        merged = {
            "filter_mode": new_config.get("filter_mode", current.get("filter_mode", FILTER_MODE_EXCLUDE)),
            "domains": new_config.get("domains", current.get("domains", [])),
            "entities": new_config.get("entities", current.get("entities", [])),
            "devices": new_config.get("devices", current.get("devices", [])),
            "overrides": new_config.get("overrides", current.get("overrides", [])),
        }

        validated_config = validate_filter_config(merged)
        await storage.async_set_filter_config(validated_config, assistant)

        connection.send_result(msg["id"], {"success": True, "filter_config": validated_config})
    except ValidationError as err:
        connection.send_error(msg["id"], "validation_error", str(err))
    except Exception as err:
        _LOGGER.error("Failed to set filter config: %s", err)
        connection.send_error(msg["id"], "filter_config_error", str(err))


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "voice_assistant_manager/set_domains",
        vol.Required("domains"): [str],
        vol.Optional("assistant"): vol.In([ASSISTANT_GOOGLE, ASSISTANT_ALEXA, ASSISTANT_HOMEKIT]),
    }
)
@websocket_api.async_response
async def websocket_set_domains(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Set domains to include/exclude for an assistant."""
    try:
        domains = validate_domains(msg["domains"])
        assistant = validate_assistant(msg.get("assistant"))

        storage = _get_storage(hass)
        await storage.async_set_domains(domains, assistant)

        connection.send_result(msg["id"], {"success": True, "domains": domains})
    except ValidationError as err:
        connection.send_error(msg["id"], "validation_error", str(err))
    except Exception as err:
        _LOGGER.error("Failed to set domains: %s", err)
        connection.send_error(msg["id"], "domains_error", str(err))


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "voice_assistant_manager/toggle_override",
        vol.Required("entity_id"): str,
        vol.Optional("assistant"): vol.In([ASSISTANT_GOOGLE, ASSISTANT_ALEXA, ASSISTANT_HOMEKIT]),
    }
)
@websocket_api.async_response
async def websocket_toggle_override(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Toggle an entity in the overrides list."""
    try:
        entity_id = validate_entity_id(msg["entity_id"])
        assistant = validate_assistant(msg.get("assistant"))

        storage = _get_storage(hass)
        added = await storage.async_toggle_override(entity_id, assistant)

        connection.send_result(msg["id"], {
            "success": True,
            "entity_id": entity_id,
            "added": added,
        })
    except ValidationError as err:
        connection.send_error(msg["id"], "validation_error", str(err))
    except Exception as err:
        _LOGGER.error("Failed to toggle override: %s", err)
        connection.send_error(msg["id"], "override_error", str(err))


# ============ Alias Endpoints ============

@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "voice_assistant_manager/set_alias",
        vol.Required("entity_id"): str,
        vol.Required("alias"): str,
        vol.Optional("assistant"): vol.In([ASSISTANT_GOOGLE, ASSISTANT_ALEXA, ASSISTANT_HOMEKIT]),
    }
)
@websocket_api.async_response
async def websocket_set_alias(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Set alias for an entity."""
    try:
        validated_entity_id = validate_entity_id(msg["entity_id"])
        validated_alias = validate_alias(msg["alias"])
        validated_assistant = validate_assistant(msg.get("assistant"))

        storage = _get_storage(hass)
        await storage.async_set_alias(
            validated_entity_id,
            validated_alias,
            validated_assistant,
        )
        connection.send_result(msg["id"], {"success": True})
    except ValidationError as err:
        connection.send_error(msg["id"], "validation_error", str(err))
    except Exception as err:
        _LOGGER.error("Failed to set alias: %s", err)
        connection.send_error(msg["id"], "alias_error", str(err))


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "voice_assistant_manager/bulk_update",
        vol.Required("action"): vol.In(
            [
                "exclude",
                "unexclude",
                "set_alias_prefix",
                "set_alias_suffix",
                "clear_alias",
                "exclude_domain",
                "exclude_device",
                "add_override",
                "remove_override",
            ]
        ),
        vol.Required("entity_ids"): vol.All([str], vol.Length(max=MAX_BULK_ENTITIES)),
        vol.Optional("value"): str,
        vol.Optional("assistant"): vol.In([ASSISTANT_GOOGLE, ASSISTANT_ALEXA, ASSISTANT_HOMEKIT]),
    }
)
@websocket_api.async_response
async def websocket_bulk_update(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Perform bulk operations on entities."""
    try:
        action = msg["action"]
        entity_ids = validate_entity_ids(msg["entity_ids"])
        value = validate_alias(msg.get("value", ""))
        assistant = validate_assistant(msg.get("assistant"))

        storage = _get_storage(hass)
        config = storage.get_filter_config(assistant)

        if action == "exclude":
            # Add entities to exclusion list
            current_entities = set(config.get("entities", []))
            current_entities.update(entity_ids)
            config["entities"] = list(current_entities)
            await storage.async_set_filter_config(config, assistant)

        elif action == "unexclude":
            # Remove entities from exclusion list
            current_entities = set(config.get("entities", []))
            current_entities -= set(entity_ids)
            config["entities"] = list(current_entities)
            await storage.async_set_filter_config(config, assistant)

        elif action == "add_override":
            # Add entities to overrides list
            current_overrides = set(config.get("overrides", []))
            current_overrides.update(entity_ids)
            config["overrides"] = list(current_overrides)
            await storage.async_set_filter_config(config, assistant)

        elif action == "remove_override":
            # Remove entities from overrides list
            current_overrides = set(config.get("overrides", []))
            current_overrides -= set(entity_ids)
            config["overrides"] = list(current_overrides)
            await storage.async_set_filter_config(config, assistant)

        elif action == "set_alias_prefix":
            ent_reg = er.async_get(hass)
            new_aliases = {}
            for entity_id in entity_ids:
                entity = ent_reg.async_get(entity_id)
                if entity:
                    state = hass.states.get(entity_id)
                    name = state.attributes.get("friendly_name") if state else None
                    name = name or entity.name or entity.original_name or entity_id
                    new_aliases[entity_id] = f"{value}{name}"
            await storage.async_set_aliases_bulk(new_aliases, assistant)

        elif action == "set_alias_suffix":
            ent_reg = er.async_get(hass)
            new_aliases = {}
            for entity_id in entity_ids:
                entity = ent_reg.async_get(entity_id)
                if entity:
                    state = hass.states.get(entity_id)
                    name = state.attributes.get("friendly_name") if state else None
                    name = name or entity.name or entity.original_name or entity_id
                    new_aliases[entity_id] = f"{name}{value}"
            await storage.async_set_aliases_bulk(new_aliases, assistant)

        elif action == "clear_alias":
            new_aliases = dict.fromkeys(entity_ids, "")
            await storage.async_set_aliases_bulk(new_aliases, assistant)

        elif action == "exclude_domain":
            domains = set()
            for entity_id in entity_ids:
                domain = entity_id.split(".")[0]
                domains.add(domain)

            current_domains = set(config.get("domains", []))
            current_domains.update(domains)
            config["domains"] = list(current_domains)
            await storage.async_set_filter_config(config, assistant)

        elif action == "exclude_device":
            ent_reg = er.async_get(hass)
            devices = set()
            for entity_id in entity_ids:
                entity = ent_reg.async_get(entity_id)
                if entity and entity.device_id:
                    devices.add(entity.device_id)

            current_devices = set(config.get("devices", []))
            current_devices.update(devices)
            config["devices"] = list(current_devices)
            await storage.async_set_filter_config(config, assistant)

        connection.send_result(msg["id"], {"success": True})

    except ValidationError as err:
        connection.send_error(msg["id"], "validation_error", str(err))
    except Exception as err:
        _LOGGER.error("Failed to perform bulk update: %s", err)
        connection.send_error(msg["id"], "bulk_update_error", str(err))


# ============ Settings Endpoints ============

@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "voice_assistant_manager/set_settings",
        vol.Required("assistant"): vol.In([ASSISTANT_GOOGLE, ASSISTANT_ALEXA]),
        vol.Required("settings"): dict,
    }
)
@websocket_api.async_response
async def websocket_set_settings(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Set assistant settings."""
    try:
        storage = _get_storage(hass)
        assistant = msg["assistant"]

        if assistant == ASSISTANT_GOOGLE:
            validated_settings = validate_google_settings(msg["settings"])
            await storage.async_set_google_settings(validated_settings)
        else:
            validated_settings = validate_alexa_settings(msg["settings"])
            await storage.async_set_alexa_settings(validated_settings)

        connection.send_result(msg["id"], {"success": True})

    except ValidationError as err:
        connection.send_error(msg["id"], "validation_error", str(err))
    except Exception as err:
        _LOGGER.error("Failed to set settings: %s", err)
        connection.send_error(msg["id"], "settings_error", str(err))


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "voice_assistant_manager/save_all",
        vol.Optional("filter_config"): {
            vol.Optional("filter_mode"): vol.In([FILTER_MODE_EXCLUDE, FILTER_MODE_INCLUDE]),
            vol.Optional("domains"): [str],
            vol.Optional("entities"): [str],
            vol.Optional("devices"): [str],
            vol.Optional("overrides"): [str],
        },
        vol.Optional("google_filter_config"): {
            vol.Optional("filter_mode"): vol.In([FILTER_MODE_EXCLUDE, FILTER_MODE_INCLUDE]),
            vol.Optional("domains"): [str],
            vol.Optional("entities"): [str],
            vol.Optional("devices"): [str],
            vol.Optional("overrides"): [str],
        },
        vol.Optional("alexa_filter_config"): {
            vol.Optional("filter_mode"): vol.In([FILTER_MODE_EXCLUDE, FILTER_MODE_INCLUDE]),
            vol.Optional("domains"): [str],
            vol.Optional("entities"): [str],
            vol.Optional("devices"): [str],
            vol.Optional("overrides"): [str],
        },
        vol.Optional("homekit_filter_config"): {
            vol.Optional("filter_mode"): vol.In([FILTER_MODE_EXCLUDE, FILTER_MODE_INCLUDE]),
            vol.Optional("domains"): [str],
            vol.Optional("entities"): [str],
            vol.Optional("devices"): [str],
            vol.Optional("overrides"): [str],
        },
        vol.Optional("aliases"): {str: str},
        vol.Optional("google_aliases"): {str: str},
        vol.Optional("alexa_aliases"): {str: str},
        vol.Optional("google_settings"): dict,
        vol.Optional("alexa_settings"): dict,
        vol.Optional("homekit_entry_id"): vol.Any(str, None),
    }
)
@websocket_api.async_response
async def websocket_save_all(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Save all configuration at once (filter configs, aliases, settings)."""
    try:
        storage = _get_storage(hass)

        # Save filter configs
        if "filter_config" in msg:
            validated_config = validate_filter_config(msg["filter_config"])
            await storage.async_set_filter_config(validated_config, None)

        if "google_filter_config" in msg:
            validated_config = validate_filter_config(msg["google_filter_config"])
            await storage.async_set_filter_config(validated_config, ASSISTANT_GOOGLE)

        if "alexa_filter_config" in msg:
            validated_config = validate_filter_config(msg["alexa_filter_config"])
            await storage.async_set_filter_config(validated_config, ASSISTANT_ALEXA)

        if "homekit_filter_config" in msg:
            validated_config = validate_filter_config(msg["homekit_filter_config"])
            await storage.async_set_filter_config(validated_config, ASSISTANT_HOMEKIT)

        # Save aliases
        if "aliases" in msg:
            await storage.async_set_aliases_bulk(msg["aliases"], None)

        if "google_aliases" in msg:
            await storage.async_set_aliases_bulk(msg["google_aliases"], ASSISTANT_GOOGLE)

        if "alexa_aliases" in msg:
            await storage.async_set_aliases_bulk(msg["alexa_aliases"], ASSISTANT_ALEXA)

        # Save settings
        if "google_settings" in msg:
            validated_settings = validate_google_settings(msg["google_settings"])
            await storage.async_set_google_settings(validated_settings)

        if "alexa_settings" in msg:
            validated_settings = validate_alexa_settings(msg["alexa_settings"])
            await storage.async_set_alexa_settings(validated_settings)

        # Save HomeKit bridge
        if "homekit_entry_id" in msg:
            entry_id = msg["homekit_entry_id"]
            if entry_id is not None:
                hk_manager = _get_homekit_manager(hass)
                bridge = hk_manager.get_bridge_config(entry_id)
                if bridge is None:
                    raise HomeKitError(f"HomeKit bridge not found: {entry_id}")
            await storage.async_set_homekit_entry_id(entry_id)

        connection.send_result(msg["id"], {"success": True})

    except ValidationError as err:
        connection.send_error(msg["id"], "validation_error", str(err))
    except HomeKitError as err:
        connection.send_error(msg["id"], "homekit_error", str(err))
    except Exception as err:
        _LOGGER.error("Failed to save all: %s", err)
        connection.send_error(msg["id"], "save_all_error", str(err))


# ============ YAML Generation Endpoints ============

@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "voice_assistant_manager/preview_yaml",
        vol.Optional("assistant"): vol.In([ASSISTANT_GOOGLE, ASSISTANT_ALEXA]),
    }
)
@websocket_api.async_response
async def websocket_preview_yaml(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Preview generated YAML without writing to files."""
    try:
        storage = _get_storage(hass)
        generator = YAMLGenerator(hass, storage)

        assistant = msg.get("assistant")
        result = {}

        if assistant is None or assistant == ASSISTANT_GOOGLE:
            google_yaml, google_warnings = generator.generate_google_yaml()
            result["google"] = {
                "yaml": google_yaml,
                "warnings": google_warnings,
                "complete": storage.is_google_complete(),
            }

        if assistant is None or assistant == ASSISTANT_ALEXA:
            alexa_yaml, alexa_warnings = generator.generate_alexa_yaml()
            result["alexa"] = {
                "yaml": alexa_yaml,
                "warnings": alexa_warnings,
                "complete": storage.is_alexa_complete(),
            }

        connection.send_result(msg["id"], result)

    except Exception as err:
        _LOGGER.error("Failed to preview YAML: %s", err)
        connection.send_error(msg["id"], "preview_error", str(err))


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "voice_assistant_manager/write_files",
    }
)
@websocket_api.async_response
async def websocket_write_files(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Write YAML files and sync HomeKit."""
    try:
        storage = _get_storage(hass)
        generator = YAMLGenerator(hass, storage)

        result = {
            "google": {"written": False, "error": None},
            "alexa": {"written": False, "error": None},
            "homekit": {"written": False, "error": None},
        }

        timestamp = datetime.now().isoformat()

        # Write Google YAML if complete
        if storage.is_google_complete():
            try:
                await generator.async_write_google_yaml()
                await storage.async_set_last_generated(ASSISTANT_GOOGLE, timestamp)
                result["google"]["written"] = True
                _LOGGER.info("Google Assistant YAML written successfully")
            except VoiceManagerError as err:
                _LOGGER.error("Failed to write Google YAML: %s", err)
                result["google"]["error"] = str(err)
            except Exception as err:
                _LOGGER.error("Failed to write Google YAML: %s", err)
                result["google"]["error"] = str(err)
        else:
            result["google"]["error"] = "Google Assistant settings incomplete or disabled"

        # Write Alexa YAML if complete
        if storage.is_alexa_complete():
            try:
                await generator.async_write_alexa_yaml()
                await storage.async_set_last_generated(ASSISTANT_ALEXA, timestamp)
                result["alexa"]["written"] = True
                _LOGGER.info("Alexa YAML written successfully")
            except VoiceManagerError as err:
                _LOGGER.error("Failed to write Alexa YAML: %s", err)
                result["alexa"]["error"] = str(err)
            except Exception as err:
                _LOGGER.error("Failed to write Alexa YAML: %s", err)
                result["alexa"]["error"] = str(err)
        else:
            result["alexa"]["error"] = "Alexa settings incomplete or disabled"

        # Sync HomeKit if bridge is configured
        if storage.is_homekit_complete():
            try:
                hk_manager = _get_homekit_manager(hass)
                await hk_manager.async_sync_from_voice_assistant_manager()
                await storage.async_set_last_generated(ASSISTANT_HOMEKIT, timestamp)
                result["homekit"]["written"] = True
                _LOGGER.info("HomeKit synced successfully")
            except HomeKitError as err:
                _LOGGER.error("Failed to sync HomeKit: %s", err)
                result["homekit"]["error"] = str(err)
            except Exception as err:
                _LOGGER.error("Failed to sync HomeKit: %s", err)
                result["homekit"]["error"] = str(err)
        else:
            result["homekit"]["error"] = "No HomeKit bridge configured"

        connection.send_result(msg["id"], result)

    except Exception as err:
        _LOGGER.error("Failed to write files: %s", err)
        connection.send_error(msg["id"], "write_error", str(err))


# ============ HomeKit Endpoints ============

@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "voice_assistant_manager/get_homekit_bridges",
    }
)
@websocket_api.async_response
async def websocket_get_homekit_bridges(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Get list of available HomeKit bridges."""
    try:
        hk_manager = _get_homekit_manager(hass)
        bridges = hk_manager.get_homekit_bridges()
        connection.send_result(msg["id"], {"bridges": bridges})
    except Exception as err:
        _LOGGER.error("Failed to get HomeKit bridges: %s", err)
        connection.send_error(msg["id"], "homekit_error", str(err))


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "voice_assistant_manager/set_homekit_bridge",
        vol.Required("entry_id"): vol.Any(str, None),
    }
)
@websocket_api.async_response
async def websocket_set_homekit_bridge(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Set which HomeKit bridge to manage."""
    try:
        entry_id = msg["entry_id"]
        storage = _get_storage(hass)

        # Validate that the entry exists if not None
        if entry_id is not None:
            hk_manager = _get_homekit_manager(hass)
            bridge = hk_manager.get_bridge_config(entry_id)
            if bridge is None:
                raise HomeKitError(f"HomeKit bridge not found: {entry_id}")

        await storage.async_set_homekit_entry_id(entry_id)
        connection.send_result(msg["id"], {"success": True, "entry_id": entry_id})
    except HomeKitError as err:
        connection.send_error(msg["id"], "homekit_error", str(err))
    except Exception as err:
        _LOGGER.error("Failed to set HomeKit bridge: %s", err)
        connection.send_error(msg["id"], "homekit_error", str(err))


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "voice_assistant_manager/sync_homekit",
    }
)
@websocket_api.async_response
async def websocket_sync_homekit(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Sync Voice Assistant Manager configuration to HomeKit bridge."""
    try:
        hk_manager = _get_homekit_manager(hass)
        result = await hk_manager.async_sync_from_voice_assistant_manager()

        # Update timestamp
        storage = _get_storage(hass)
        await storage.async_set_last_generated(ASSISTANT_HOMEKIT, datetime.now().isoformat())

        connection.send_result(msg["id"], result)
    except HomeKitError as err:
        connection.send_error(msg["id"], "homekit_error", str(err))
    except Exception as err:
        _LOGGER.error("Failed to sync HomeKit: %s", err)
        connection.send_error(msg["id"], "homekit_error", str(err))


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "voice_assistant_manager/import_homekit",
    }
)
@websocket_api.async_response
async def websocket_import_homekit(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Import current HomeKit configuration into Voice Assistant Manager."""
    try:
        hk_manager = _get_homekit_manager(hass)
        result = await hk_manager.async_import_from_homekit()
        connection.send_result(msg["id"], result)
    except HomeKitError as err:
        connection.send_error(msg["id"], "homekit_error", str(err))
    except Exception as err:
        _LOGGER.error("Failed to import from HomeKit: %s", err)
        connection.send_error(msg["id"], "homekit_error", str(err))


# ============ System Endpoints ============

@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "voice_assistant_manager/check_config",
    }
)
@websocket_api.async_response
async def websocket_check_config(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Call homeassistant.check_config service."""
    try:
        await hass.services.async_call(
            "homeassistant",
            "check_config",
            blocking=True,
        )
        connection.send_result(msg["id"], {"success": True})
    except Exception as err:
        _LOGGER.error("Configuration check failed: %s", err)
        connection.send_result(msg["id"], {"success": False, "error": str(err)})


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "voice_assistant_manager/restart",
    }
)
@websocket_api.async_response
async def websocket_restart(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Call homeassistant.restart service."""
    try:
        await hass.services.async_call(
            "homeassistant",
            "restart",
            blocking=False,
        )
        connection.send_result(msg["id"], {"success": True})
        _LOGGER.info("Home Assistant restart initiated")
    except Exception as err:
        _LOGGER.error("Failed to restart: %s", err)
        connection.send_result(msg["id"], {"success": False, "error": str(err)})
