"""MCP tools for UniFi Protect NVR read operations."""

from __future__ import annotations

from typing import Any

from ..api import ProtectClient
from ..config import Settings
from ..models.protect_nvr import ProtectNVR
from ..utils import ValidationError, get_logger, sanitize_log_message
from ..utils.exceptions import ResourceNotFoundError
from ..utils.tool_kind import read_tool


def _validate_nvr_id(nvr_id: str) -> str:
    nvr_id = nvr_id.strip()
    if not nvr_id:
        raise ValidationError("nvr_id is required")
    return nvr_id


@read_tool
async def list_protect_nvrs(settings: Settings) -> dict[str, Any]:
    """List UniFi Protect NVRs."""
    logger = get_logger(__name__, settings.log_level)

    async with ProtectClient(settings) as client:
        await client.authenticate()
        response = await client.get(settings.get_protect_integration_path("nvrs"))

    if isinstance(response, list):
        data = response
        count = len(data)
        total_count = count
    elif isinstance(response, dict) and "data" not in response and "id" in response:
        # Spec 7.3.70: GET /v1/nvrs returns the one NVR object.
        data = [response]
        count = total_count = 1
    elif isinstance(response, dict):
        data = response.get("data", [])
        count = response.get("count", len(data))
        total_count = response.get("totalCount", len(data))
    else:
        raise ValueError(f"Unexpected Protect inventory response type: {type(response).__name__}")

    nvrs = [ProtectNVR.model_validate(item).model_dump(by_alias=True) for item in data]
    logger.info(sanitize_log_message(f"Listed {len(nvrs)} Protect NVRs"))

    return {
        "count": count,
        "totalCount": total_count,
        "data": nvrs,
    }


@read_tool
async def get_protect_nvr(nvr_id: str, settings: Settings) -> dict[str, Any]:
    """Get a single UniFi Protect NVR.

    The Protect API has no ``nvrs/{id}`` route: ``GET nvrs`` returns the
    console's one NVR. This reads that route and checks ``nvr_id`` against it.
    """
    logger = get_logger(__name__, settings.log_level)
    nvr_id = _validate_nvr_id(nvr_id)

    async with ProtectClient(settings) as client:
        await client.authenticate()
        response = await client.get(settings.get_protect_integration_path("nvrs"))

    if isinstance(response, dict) and "data" in response:
        response = response["data"]
    items = response if isinstance(response, list) else [response]
    nvr_data = next(
        (item for item in items if isinstance(item, dict) and item.get("id") == nvr_id), None
    )
    if nvr_data is None:
        raise ResourceNotFoundError("Protect NVR", nvr_id)
    nvr = ProtectNVR.model_validate(nvr_data)
    logger.info(sanitize_log_message(f"Retrieved Protect NVR {nvr_id}"))
    return nvr.model_dump(by_alias=True)
