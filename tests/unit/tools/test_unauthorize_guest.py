"""Tests for unauthorize_guest (gap N12): UNAUTHORIZE_GUEST_ACCESS client action."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.tools.client_management as cm_module
from src.utils.exceptions import ValidationError


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.log_level = "INFO"
    return settings


@pytest.mark.asyncio
async def test_unauthorize_guest_posts_spec_action(mock_settings):
    from src.tools.client_management import unauthorize_guest

    revoked = {"authorizationMethod": "API", "expiresAt": "2026-10-25T12:00:00Z"}
    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.post = AsyncMock(
        return_value={"action": "UNAUTHORIZE_GUEST_ACCESS", "revokedAuthorization": revoked}
    )
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch.object(cm_module, "UniFiClient", return_value=mock_client):
        result = await unauthorize_guest("default", "guest-uuid", mock_settings, confirm=True)

    mock_client.post.assert_awaited_once_with(
        "/integration/v1/sites/default/clients/guest-uuid/actions",
        json_data={"action": "UNAUTHORIZE_GUEST_ACCESS"},
    )
    assert result == {
        "success": True,
        "client_id": "guest-uuid",
        "revoked_authorization": revoked,
    }


@pytest.mark.asyncio
async def test_unauthorize_guest_dry_run_and_confirm(mock_settings):
    from src.tools.client_management import unauthorize_guest

    with patch.object(cm_module, "UniFiClient") as cls:
        preview = await unauthorize_guest("default", "guest-uuid", mock_settings, dry_run=True)
        with pytest.raises(ValidationError):
            await unauthorize_guest("default", "guest-uuid", mock_settings, confirm="false")
        with pytest.raises(ValidationError):
            await unauthorize_guest("default", " ", mock_settings, confirm=True)
    cls.assert_not_called()
    assert preview == {
        "dry_run": True,
        "operation": "unauthorize_guest",
        "client_id": "guest-uuid",
        "payload": {"action": "UNAUTHORIZE_GUEST_ACCESS"},
    }
