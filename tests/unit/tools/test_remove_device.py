"""Tests for remove_device (gap N10): DELETE /v1/sites/{site}/devices/{id}."""

from unittest.mock import AsyncMock, patch

import pytest

from src.config import Settings
from src.utils.exceptions import ValidationError

DEVICE_UUID = "88888888-8888-8888-8888-888888888888"
LEGACY_ID = "507f1f77bcf86cd799439011"  # pragma: allowlist secret
PATH = f"/proxy/network/integration/v1/sites/site-uuid/devices/{DEVICE_UUID}"


@pytest.fixture
def local_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("UNIFI_API_KEY", "test-api-key")
    monkeypatch.setenv("UNIFI_API_TYPE", "local")
    monkeypatch.setenv("UNIFI_LOCAL_HOST", "192.0.2.1")
    return Settings()


@pytest.mark.asyncio
async def test_remove_device_deletes_integration_route(local_settings):
    from src.tools.devices import remove_device

    client = AsyncMock()
    client.authenticate = AsyncMock()
    client.resolve_site_id = AsyncMock(return_value="site-uuid")
    client.delete = AsyncMock(return_value={})
    with patch("src.tools.devices.UniFiClient") as cls:
        cls.return_value.__aenter__.return_value = client
        cls.return_value.__aexit__.return_value = False
        result = await remove_device("default", DEVICE_UUID, local_settings, confirm=True)

    client.delete.assert_awaited_once_with(PATH)
    assert result == {"success": True, "device_id": DEVICE_UUID}


@pytest.mark.asyncio
async def test_remove_device_dry_run_and_confirm(local_settings):
    from src.tools.devices import remove_device

    with patch("src.tools.devices.UniFiClient") as cls:
        preview = await remove_device("default", DEVICE_UUID, local_settings, dry_run=True)
        with pytest.raises(ValidationError):
            await remove_device("default", DEVICE_UUID, local_settings, confirm="false")
    cls.assert_not_called()
    assert preview == {"dry_run": True, "operation": "remove_device", "device_id": DEVICE_UUID}


@pytest.mark.asyncio
async def test_remove_device_needs_uuid(local_settings):
    from src.tools.devices import remove_device

    with patch("src.tools.devices.UniFiClient") as cls:
        with pytest.raises(ValidationError):
            await remove_device("default", LEGACY_ID, local_settings, confirm=True)
    cls.assert_not_called()
