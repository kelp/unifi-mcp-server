"""Tests for ACL rule ordering tools (gap N5).

Routes: GET and PUT /v1/sites/{site}/acl-rules/ordering with body
{"orderedAclRuleIds": [...]}.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.config import Settings
from src.utils.exceptions import ValidationError

PATH = "/proxy/network/integration/v1/sites/site-uuid/acl-rules/ordering"


@pytest.fixture
def local_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("UNIFI_API_KEY", "test-api-key")
    monkeypatch.setenv("UNIFI_API_TYPE", "local")
    monkeypatch.setenv("UNIFI_LOCAL_HOST", "192.0.2.1")
    return Settings()


@pytest.fixture
def client():
    mock = AsyncMock()
    mock.is_authenticated = True
    mock.resolve_site_id = AsyncMock(return_value="site-uuid")
    return mock


def _patched(client):
    cls = patch("src.tools.acls.UniFiClient")
    started = cls.start()
    started.return_value.__aenter__.return_value = client
    started.return_value.__aexit__.return_value = False
    return cls


@pytest.mark.asyncio
async def test_get_acl_rule_ordering(local_settings, client):
    from src.tools.acls import get_acl_rule_ordering

    client.get = AsyncMock(return_value={"orderedAclRuleIds": ["a", "b"]})
    cls = _patched(client)
    try:
        result = await get_acl_rule_ordering("default", local_settings)
    finally:
        cls.stop()

    client.get.assert_awaited_once_with(PATH)
    assert result == {"site_id": "default", "ordered_acl_rule_ids": ["a", "b"]}


@pytest.mark.asyncio
async def test_reorder_acl_rules(local_settings, client):
    from src.tools.acls import reorder_acl_rules

    client.put = AsyncMock(return_value={"orderedAclRuleIds": ["b", "a"]})
    cls = _patched(client)
    try:
        result = await reorder_acl_rules("default", ["b", "a"], local_settings, confirm=True)
    finally:
        cls.stop()

    client.put.assert_awaited_once_with(PATH, json_data={"orderedAclRuleIds": ["b", "a"]})
    assert result == {"site_id": "default", "ordered_acl_rule_ids": ["b", "a"]}


@pytest.mark.asyncio
async def test_reorder_acl_rules_dry_run(local_settings):
    from src.tools.acls import reorder_acl_rules

    with patch("src.tools.acls.UniFiClient") as cls:
        result = await reorder_acl_rules("default", ["a"], local_settings, dry_run=True)
    cls.assert_not_called()
    assert result == {
        "dry_run": True,
        "operation": "reorder_acl_rules",
        "payload": {"orderedAclRuleIds": ["a"]},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("confirm", [False, "false"])
async def test_reorder_acl_rules_requires_confirm(local_settings, confirm):
    from src.tools.acls import reorder_acl_rules

    with patch("src.tools.acls.UniFiClient") as cls:
        with pytest.raises(ValidationError):
            await reorder_acl_rules("default", ["a"], local_settings, confirm=confirm)
    cls.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("ids", [[], ["a", "a"], ["a", " "]])
async def test_reorder_acl_rules_rejects_bad_list(local_settings, ids):
    from src.tools.acls import reorder_acl_rules

    with patch("src.tools.acls.UniFiClient") as cls:
        with pytest.raises(ValidationError):
            await reorder_acl_rules("default", ids, local_settings, confirm=True)
    cls.assert_not_called()
