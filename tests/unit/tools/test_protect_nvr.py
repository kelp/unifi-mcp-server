"""Unit tests for UniFi Protect NVR tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tools.protect_nvr import get_protect_nvr, list_protect_nvrs
from src.utils.exceptions import ValidationError


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.log_level = "INFO"
    settings.get_protect_integration_path = MagicMock(
        side_effect=lambda endpoint: f"/integration/v1/{endpoint.lstrip('/')}"
    )
    return settings


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.authenticate = AsyncMock()
    client.get = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


@pytest.mark.asyncio
async def test_list_protect_nvrs_success(mock_settings, mock_client):
    mock_response = {
        "count": 1,
        "totalCount": 1,
        "data": [
            {
                "id": "nvr-1",
                "name": "Main NVR",
                "model": "UNVR",
                "firmwareVersion": "4.0.21",
                "uptime": 12345,
            }
        ],
    }
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("src.tools.protect_nvr.ProtectClient", return_value=mock_client):
        result = await list_protect_nvrs(mock_settings)

    mock_client.authenticate.assert_awaited_once()
    mock_client.get.assert_awaited_once_with("/integration/v1/nvrs")
    assert result["count"] == 1
    assert result["data"][0]["id"] == "nvr-1"
    assert result["data"][0]["name"] == "Main NVR"


@pytest.mark.asyncio
async def test_get_protect_nvr_success(mock_settings, mock_client):
    mock_response = {
        "id": "nvr-1",
        "name": "Main NVR",
        "model": "UNVR",
        "firmwareVersion": "4.0.21",
        "uptime": 12345,
    }
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("src.tools.protect_nvr.ProtectClient", return_value=mock_client):
        result = await get_protect_nvr("nvr-1", mock_settings)

    mock_client.authenticate.assert_awaited_once()
    mock_client.get.assert_awaited_once_with("/integration/v1/nvrs")
    assert result["id"] == "nvr-1"
    assert result["model"] == "UNVR"


@pytest.mark.asyncio
async def test_get_protect_nvr_empty_id_raises(mock_settings):
    with pytest.raises(ValidationError, match="nvr_id"):
        await get_protect_nvr("", mock_settings)


@pytest.mark.asyncio
async def test_list_protect_nvrs_top_level_array(mock_settings, mock_client):
    mock_client.get = AsyncMock(
        return_value=[{"id": "nvr-1", "name": "Protect NVR", "model": "UNVR"}]
    )

    with patch("src.tools.protect_nvr.ProtectClient", return_value=mock_client):
        result = await list_protect_nvrs(mock_settings)

    assert result["count"] == 1
    assert result["totalCount"] == 1
    assert len(result["data"]) == 1


@pytest.mark.asyncio
async def test_list_protect_nvrs_unexpected_response_raises(mock_settings, mock_client):
    mock_client.get = AsyncMock(return_value=None)

    with patch("src.tools.protect_nvr.ProtectClient", return_value=mock_client):
        with pytest.raises(ValueError, match="Unexpected Protect inventory response type"):
            await list_protect_nvrs(mock_settings)


# Spec 7.3.70: GET /v1/nvrs returns ONE NVR object, not a list or envelope.
_SPEC_NVR = {
    "id": "nvr-1",
    "modelKey": "nvr",
    "name": "UCG Fiber",
    "type": "UCG-Fiber",
    "guid": None,
    "mac": "AABBCCDDEEFF",
    "doorbellSettings": {"defaultMessageText": "Welcome"},
    "armMode": {"status": "disabled", "armProfileId": None},
}


@pytest.mark.asyncio
async def test_list_protect_nvrs_single_object_reply(mock_settings, mock_client):
    mock_client.get = AsyncMock(return_value=dict(_SPEC_NVR))

    with patch("src.tools.protect_nvr.ProtectClient", return_value=mock_client):
        result = await list_protect_nvrs(mock_settings)

    assert result["count"] == 1
    assert result["totalCount"] == 1
    nvr = result["data"][0]
    assert nvr["id"] == "nvr-1"
    assert nvr["modelKey"] == "nvr"
    assert nvr["type"] == "UCG-Fiber"
    assert nvr["mac"] == "AABBCCDDEEFF"
    assert nvr["armMode"]["status"] == "disabled"
    assert nvr["doorbellSettings"]["defaultMessageText"] == "Welcome"


@pytest.mark.asyncio
async def test_get_protect_nvr_reads_singleton_route(mock_settings, mock_client):
    """The spec has no nvrs/{id}; read /nvrs and check the id."""
    mock_client.get = AsyncMock(return_value=dict(_SPEC_NVR))

    with patch("src.tools.protect_nvr.ProtectClient", return_value=mock_client):
        result = await get_protect_nvr("nvr-1", mock_settings)

    mock_client.get.assert_awaited_once_with("/integration/v1/nvrs")
    assert result["id"] == "nvr-1"
    assert result["type"] == "UCG-Fiber"


@pytest.mark.asyncio
async def test_get_protect_nvr_unknown_id_raises(mock_settings, mock_client):
    from src.utils.exceptions import ResourceNotFoundError

    mock_client.get = AsyncMock(return_value=dict(_SPEC_NVR))

    with patch("src.tools.protect_nvr.ProtectClient", return_value=mock_client):
        with pytest.raises(ResourceNotFoundError):
            await get_protect_nvr("other", mock_settings)
