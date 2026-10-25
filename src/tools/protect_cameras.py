"""MCP tools for UniFi Protect camera read operations."""

from __future__ import annotations

import base64
from typing import Any

from ..api import ProtectClient
from ..config import Settings
from ..models import ProtectCamera
from ..utils import ValidationError, get_logger, sanitize_log_message, validate_limit_offset
from ..utils.tool_kind import read_tool, write_tool
from ..utils.validators import coerce_bool, validate_confirmation


def _validate_camera_id(camera_id: str) -> str:
    camera_id = camera_id.strip()
    if not camera_id:
        raise ValidationError("camera_id is required")
    return camera_id


@read_tool
async def list_protect_cameras(
    settings: Settings,
    limit: int | None = None,
    offset: int | None = None,
) -> dict[str, Any]:
    """List UniFi Protect cameras.

    The Protect API returns every camera in one array and takes no paging
    parameters, so ``limit`` and ``offset`` page that array here.
    """
    logger = get_logger(__name__, settings.log_level)
    final_limit, final_offset = validate_limit_offset(limit, offset)

    async with ProtectClient(settings) as client:
        await client.authenticate()
        response = await client.get(settings.get_protect_integration_path("cameras"))

    if isinstance(response, list):
        total_count = len(response)
        data = response[final_offset : final_offset + final_limit]
        count = len(data)
    elif isinstance(response, dict):
        data = response.get("data", [])
        count = response.get("count", len(data))
        total_count = response.get("totalCount", len(data))
    else:
        raise ValueError(f"Unexpected Protect inventory response type: {type(response).__name__}")

    cameras = [ProtectCamera.model_validate(item).model_dump(by_alias=True) for item in data]
    logger.info(sanitize_log_message(f"Listed {len(cameras)} Protect cameras"))

    return {
        "offset": final_offset,
        "limit": final_limit,
        "count": count,
        "totalCount": total_count,
        "data": cameras,
    }


@read_tool
async def get_protect_camera(camera_id: str, settings: Settings) -> dict[str, Any]:
    """Get a single UniFi Protect camera."""
    logger = get_logger(__name__, settings.log_level)
    camera_id = _validate_camera_id(camera_id)

    async with ProtectClient(settings) as client:
        await client.authenticate()
        response = await client.get(settings.get_protect_integration_path(f"cameras/{camera_id}"))

    camera_data = response.get("data", response) if isinstance(response, dict) else response
    camera = ProtectCamera.model_validate(camera_data)
    logger.info(sanitize_log_message(f"Retrieved Protect camera {camera_id}"))
    return camera.model_dump(by_alias=True)


_VIDEO_MODES = ("default", "highFps", "sport", "slowShutter", "lprReflex", "lprNoneReflex")
_HDR_TYPES = ("auto", "on", "off")
_RTSPS_QUALITIES = ("high", "medium", "low", "package")


def _validate_qualities(qualities: list[str]) -> list[str]:
    if not qualities:
        raise ValidationError("qualities must list at least one of: high, medium, low, package")
    bad = [q for q in qualities if q not in _RTSPS_QUALITIES]
    if bad:
        raise ValidationError(
            f"Unknown RTSPS qualities {bad}; use high, medium, low or package "
            "(package needs a camera with hasPackageCamera)"
        )
    return list(qualities)


@write_tool
async def update_protect_camera(
    camera_id: str,
    settings: Settings,
    name: str | None = None,
    osd_settings: dict[str, Any] | None = None,
    led_settings: dict[str, Any] | None = None,
    lcd_message: dict[str, Any] | None = None,
    mic_volume: int | None = None,
    video_mode: str | None = None,
    hdr_type: str | None = None,
    smart_detect_settings: dict[str, Any] | None = None,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Update Protect camera settings (PATCH cameras/{id}).

    Args:
        camera_id: Protect camera identifier
        settings: Application settings
        name: New display name
        osd_settings: On-screen display, e.g. {"isNameEnabled": true,
            "isDateEnabled": true, "isLogoEnabled": false,
            "overlayLocation": "topLeft"}
        led_settings: e.g. {"isEnabled": true, "welcomeLed": false, "floodLed": false}
        lcd_message: Doorbell LCD message, e.g. {"type": "CUSTOM_MESSAGE",
            "text": "Back soon", "resetAt": null}. Types: LEAVE_PACKAGE_AT_DOOR,
            DO_NOT_DISTURB, CUSTOM_MESSAGE, IMAGE.
        mic_volume: Microphone volume, 0-100
        video_mode: default, highFps, sport, slowShutter, lprReflex or lprNoneReflex
        hdr_type: auto, on or off
        smart_detect_settings: e.g. {"objectTypes": ["person"], "audioTypes": []}
        confirm: Must be true to apply the change (required unless dry_run)
        dry_run: Preview the change without applying it

    Returns:
        The updated camera as returned by the controller
    """
    validate_confirmation(confirm, "update Protect camera", dry_run)
    logger = get_logger(__name__, settings.log_level)
    camera_id = _validate_camera_id(camera_id)

    if mic_volume is not None and not 0 <= mic_volume <= 100:
        raise ValidationError("mic_volume must be between 0 and 100")
    if video_mode is not None and video_mode not in _VIDEO_MODES:
        raise ValidationError(f"video_mode must be one of: {', '.join(_VIDEO_MODES)}")
    if hdr_type is not None and hdr_type not in _HDR_TYPES:
        raise ValidationError(f"hdr_type must be one of: {', '.join(_HDR_TYPES)}")

    payload: dict[str, Any] = {}
    for key, value in (
        ("name", name),
        ("osdSettings", osd_settings),
        ("ledSettings", led_settings),
        ("lcdMessage", lcd_message),
        ("micVolume", mic_volume),
        ("videoMode", video_mode),
        ("hdrType", hdr_type),
        ("smartDetectSettings", smart_detect_settings),
    ):
        if value is not None:
            payload[key] = value

    if not payload:
        raise ValidationError(
            "No updates provided: pass at least one of name, osd_settings, led_settings, "
            "lcd_message, mic_volume, video_mode, hdr_type, smart_detect_settings"
        )

    if coerce_bool(dry_run):
        return {
            "dry_run": True,
            "operation": "update_protect_camera",
            "camera_id": camera_id,
            "payload": payload,
        }

    async with ProtectClient(settings) as client:
        await client.authenticate()
        response = await client.patch(
            settings.get_protect_integration_path(f"cameras/{camera_id}"),
            json_data=payload,
        )

    camera_data = response.get("data", response) if isinstance(response, dict) else response
    camera = ProtectCamera.model_validate(camera_data)
    logger.info(sanitize_log_message(f"Updated Protect camera {camera_id}"))
    return camera.model_dump(by_alias=True)


@write_tool
async def create_protect_camera_rtsps_stream(
    camera_id: str,
    settings: Settings,
    qualities: list[str],
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Create RTSPS stream URLs for a camera (POST cameras/{id}/rtsps-stream).

    The returned URLs give live video to anyone who has them. Treat them as
    secrets: do not paste them into logs or tickets.

    Args:
        camera_id: Protect camera identifier
        settings: Application settings
        qualities: One or more of high, medium, low, package (package needs a
            camera with hasPackageCamera)
        confirm: Must be true to create the streams (required unless dry_run)
        dry_run: Preview the request without sending it

    Returns:
        {"success", "camera_id", "streams": {quality: rtsps URL}}
    """
    validate_confirmation(confirm, "create Protect camera RTSPS stream", dry_run)
    logger = get_logger(__name__, settings.log_level)
    camera_id = _validate_camera_id(camera_id)
    payload = {"qualities": _validate_qualities(qualities)}

    if coerce_bool(dry_run):
        return {
            "dry_run": True,
            "operation": "create_protect_camera_rtsps_stream",
            "camera_id": camera_id,
            "payload": payload,
        }

    async with ProtectClient(settings) as client:
        await client.authenticate()
        response = await client.post(
            settings.get_protect_integration_path(f"cameras/{camera_id}/rtsps-stream"),
            json_data=payload,
        )

    # Log the qualities only, never the URLs.
    logger.info(
        sanitize_log_message(f"Created RTSPS streams {payload['qualities']} on {camera_id}")
    )
    return {
        "success": True,
        "camera_id": camera_id,
        "streams": response if isinstance(response, dict) else {},
    }


@read_tool
async def get_protect_camera_rtsps_streams(camera_id: str, settings: Settings) -> dict[str, Any]:
    """Get the existing RTSPS stream URLs for a camera (GET cameras/{id}/rtsps-stream).

    The URLs give live video to anyone who has them. Treat them as secrets.

    Args:
        camera_id: Protect camera identifier
        settings: Application settings

    Returns:
        {"camera_id", "streams": {"high", "medium", "low", "package"}}; a
        quality with no stream is null
    """
    logger = get_logger(__name__, settings.log_level)
    camera_id = _validate_camera_id(camera_id)

    async with ProtectClient(settings) as client:
        await client.authenticate()
        response = await client.get(
            settings.get_protect_integration_path(f"cameras/{camera_id}/rtsps-stream")
        )

    logger.info(sanitize_log_message(f"Retrieved RTSPS streams for Protect camera {camera_id}"))
    return {"camera_id": camera_id, "streams": response if isinstance(response, dict) else {}}


@write_tool
async def delete_protect_camera_rtsps_stream(
    camera_id: str,
    settings: Settings,
    qualities: list[str],
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Revoke RTSPS streams for a camera (DELETE cameras/{id}/rtsps-stream).

    Clients that use the revoked URLs lose the stream.

    Args:
        camera_id: Protect camera identifier
        settings: Application settings
        qualities: One or more of high, medium, low, package to remove
        confirm: Must be true to remove the streams (required unless dry_run)
        dry_run: Preview the request without sending it

    Returns:
        {"success", "camera_id", "removed": [qualities]}
    """
    validate_confirmation(confirm, "delete Protect camera RTSPS stream", dry_run)
    logger = get_logger(__name__, settings.log_level)
    camera_id = _validate_camera_id(camera_id)
    params = {"qualities": _validate_qualities(qualities)}

    if coerce_bool(dry_run):
        return {
            "dry_run": True,
            "operation": "delete_protect_camera_rtsps_stream",
            "camera_id": camera_id,
            "params": params,
        }

    async with ProtectClient(settings) as client:
        await client.authenticate()
        await client.delete(
            settings.get_protect_integration_path(f"cameras/{camera_id}/rtsps-stream"),
            params=params,
        )

    logger.info(sanitize_log_message(f"Removed RTSPS streams {params['qualities']} on {camera_id}"))
    return {"success": True, "camera_id": camera_id, "removed": params["qualities"]}


@read_tool
async def get_protect_camera_snapshot(
    camera_id: str,
    settings: Settings,
    channel: str | None = None,
    high_quality: bool | None = None,
) -> dict[str, Any]:
    """Get a still image from a camera (GET cameras/{id}/snapshot).

    Args:
        camera_id: Protect camera identifier
        settings: Application settings
        channel: ``package`` for the package camera of a camera with
            ``hasPackageCamera: true``; omit for the main camera
        high_quality: Force a 1080p or higher snapshot

    Returns:
        {"camera_id", "content_type", "size_bytes", "image_base64"}
    """
    logger = get_logger(__name__, settings.log_level)
    camera_id = _validate_camera_id(camera_id)
    params: dict[str, Any] = {}
    if channel:
        params["channel"] = channel.strip()
    if high_quality is not None:
        params["highQuality"] = "true" if coerce_bool(high_quality) else "false"

    async with ProtectClient(settings) as client:
        await client.authenticate()
        body, content_type = await client.get_bytes(
            settings.get_protect_integration_path(f"cameras/{camera_id}/snapshot"),
            params=params,
        )

    logger.info(sanitize_log_message(f"Retrieved {len(body)} byte snapshot from {camera_id}"))
    return {
        "camera_id": camera_id,
        "content_type": content_type,
        "size_bytes": len(body),
        "image_base64": base64.b64encode(body).decode("ascii"),
    }


async def _post_ptz(
    settings: Settings, camera_id: str, suffix: str, operation: str, **ids: Any
) -> dict[str, Any]:
    async with ProtectClient(settings) as client:
        await client.authenticate()
        response = await client.post(
            settings.get_protect_integration_path(f"cameras/{camera_id}/ptz/{suffix}")
        )
    get_logger(__name__, settings.log_level).info(
        sanitize_log_message(f"{operation} on camera {camera_id}")
    )
    return {"success": True, "camera_id": camera_id, **ids, "response": response}


@write_tool
async def goto_protect_camera_ptz_preset(
    camera_id: str,
    settings: Settings,
    slot: int,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Move a PTZ camera to a preset position (POST cameras/{id}/ptz/goto/{slot}).

    The camera moves, so it can stop watching what it watches now.

    Args:
        camera_id: Protect camera identifier
        settings: Application settings
        slot: Preset slot: -1 for the home preset, 0 or more for other presets
        confirm: Must be true to move the camera (required unless dry_run)
        dry_run: Preview the request without sending it

    Returns:
        {"success", "camera_id", "slot", "response"}
    """
    validate_confirmation(confirm, "move Protect camera to PTZ preset", dry_run)
    camera_id = _validate_camera_id(camera_id)
    if not isinstance(slot, int) or slot < -1:
        raise ValidationError("slot must be -1 (home) or a preset number of 0 or more")
    if coerce_bool(dry_run):
        return {
            "dry_run": True,
            "operation": "goto_protect_camera_ptz_preset",
            "camera_id": camera_id,
            "slot": slot,
        }
    return await _post_ptz(
        settings, camera_id, f"goto/{slot}", "goto_protect_camera_ptz_preset", slot=slot
    )


@write_tool
async def start_protect_camera_ptz_patrol(
    camera_id: str,
    settings: Settings,
    slot: int,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Start a PTZ patrol on a camera (POST cameras/{id}/ptz/patrol/start/{slot}).

    Args:
        camera_id: Protect camera identifier
        settings: Application settings
        slot: Patrol slot, 0 to 4
        confirm: Must be true to start the patrol (required unless dry_run)
        dry_run: Preview the request without sending it

    Returns:
        {"success", "camera_id", "slot", "response"}
    """
    validate_confirmation(confirm, "start Protect camera PTZ patrol", dry_run)
    camera_id = _validate_camera_id(camera_id)
    if not isinstance(slot, int) or not 0 <= slot <= 4:
        raise ValidationError("slot must be a patrol number from 0 to 4")
    if coerce_bool(dry_run):
        return {
            "dry_run": True,
            "operation": "start_protect_camera_ptz_patrol",
            "camera_id": camera_id,
            "slot": slot,
        }
    return await _post_ptz(
        settings, camera_id, f"patrol/start/{slot}", "start_protect_camera_ptz_patrol", slot=slot
    )


@write_tool
async def stop_protect_camera_ptz_patrol(
    camera_id: str,
    settings: Settings,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Stop the active PTZ patrol on a camera (POST cameras/{id}/ptz/patrol/stop).

    Args:
        camera_id: Protect camera identifier
        settings: Application settings
        confirm: Must be true to stop the patrol (required unless dry_run)
        dry_run: Preview the request without sending it

    Returns:
        {"success", "camera_id", "response"}
    """
    validate_confirmation(confirm, "stop Protect camera PTZ patrol", dry_run)
    camera_id = _validate_camera_id(camera_id)
    if coerce_bool(dry_run):
        return {
            "dry_run": True,
            "operation": "stop_protect_camera_ptz_patrol",
            "camera_id": camera_id,
        }
    return await _post_ptz(settings, camera_id, "patrol/stop", "stop_protect_camera_ptz_patrol")
