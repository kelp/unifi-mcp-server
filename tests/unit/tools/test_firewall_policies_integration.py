"""Tests for the integration-API firewall policy tools (gaps N3, N4).

Routes: GET /v1/sites/{site}/firewall/policies[/{id}], PATCH /{id}
(loggingEnabled), GET/PUT /firewall/policies/ordering.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.config import Settings
from src.utils.exceptions import ValidationError

BASE = "/proxy/network/integration/v1/sites/site-uuid/firewall/policies"
SRC_ZONE = "11111111-1111-1111-1111-111111111111"
DST_ZONE = "22222222-2222-2222-2222-222222222222"

_POLICY = {
    "id": "33333333-3333-3333-3333-333333333333",
    "name": "Allow LAN to IoT",
    "enabled": True,
    "action": {"type": "ALLOW", "allowReturnTraffic": True},
    "source": {"zoneId": SRC_ZONE, "trafficFilter": {"type": "NETWORK"}},
    "destination": {"zoneId": DST_ZONE},
    "ipProtocolScope": {"ipVersion": "IPV4_AND_IPV6"},
    "connectionStateFilter": ["NEW"],
    "loggingEnabled": False,
    "metadata": {"origin": "USER_DEFINED"},
}


@pytest.fixture
def local_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("UNIFI_API_KEY", "test-api-key")
    monkeypatch.setenv("UNIFI_API_TYPE", "local")
    monkeypatch.setenv("UNIFI_LOCAL_HOST", "192.168.2.1")
    return Settings()


@pytest.fixture
def cloud_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("UNIFI_API_KEY", "test-api-key")
    monkeypatch.setenv("UNIFI_API_TYPE", "cloud-ea")
    monkeypatch.delenv("UNIFI_LOCAL_HOST", raising=False)
    return Settings()


@pytest.fixture
def client():
    mock = AsyncMock()
    mock.is_authenticated = True
    mock.resolve_site_id = AsyncMock(return_value="site-uuid")
    return mock


def _patched(client):
    cls = patch("src.tools.firewall_policies.UniFiClient")
    started = cls.start()
    started.return_value.__aenter__.return_value = client
    started.return_value.__aexit__.return_value = False
    return cls, started


@pytest.mark.asyncio
async def test_list_integration_firewall_policies(local_settings, client):
    from src.tools.firewall_policies import list_integration_firewall_policies

    client.get = AsyncMock(
        return_value={"offset": 0, "limit": 25, "count": 1, "totalCount": 1, "data": [_POLICY]}
    )
    cls, _ = _patched(client)
    try:
        result = await list_integration_firewall_policies(
            "default", local_settings, limit=25, filter="name.like('Allow*')"
        )
    finally:
        cls.stop()

    client.get.assert_awaited_once_with(
        BASE, params={"limit": 25, "offset": 0, "filter": "name.like('Allow*')"}
    )
    assert result["count"] == 1
    assert result["totalCount"] == 1
    assert result["data"][0]["action"]["allowReturnTraffic"] is True
    assert result["data"][0]["connectionStateFilter"] == ["NEW"]


@pytest.mark.asyncio
async def test_list_integration_firewall_policies_cloud_refused(cloud_settings):
    from src.tools.firewall_policies import list_integration_firewall_policies

    with pytest.raises(NotImplementedError):
        await list_integration_firewall_policies("default", cloud_settings)


@pytest.mark.asyncio
async def test_get_integration_firewall_policy(local_settings, client):
    from src.tools.firewall_policies import get_integration_firewall_policy

    client.get = AsyncMock(return_value=dict(_POLICY))
    cls, _ = _patched(client)
    try:
        result = await get_integration_firewall_policy("default", _POLICY["id"], local_settings)
    finally:
        cls.stop()

    client.get.assert_awaited_once_with(f"{BASE}/{_POLICY['id']}")
    assert result == _POLICY


@pytest.mark.asyncio
async def test_get_firewall_policy_ordering(local_settings, client):
    from src.tools.firewall_policies import get_firewall_policy_ordering

    ordering = {
        "orderedFirewallPolicyIds": {"beforeSystemDefined": ["a"], "afterSystemDefined": []}
    }
    client.get = AsyncMock(return_value=ordering)
    cls, _ = _patched(client)
    try:
        result = await get_firewall_policy_ordering("default", SRC_ZONE, DST_ZONE, local_settings)
    finally:
        cls.stop()

    client.get.assert_awaited_once_with(
        f"{BASE}/ordering",
        params={"sourceFirewallZoneId": SRC_ZONE, "destinationFirewallZoneId": DST_ZONE},
    )
    assert result == {
        "source_zone_id": SRC_ZONE,
        "destination_zone_id": DST_ZONE,
        "before_system_defined": ["a"],
        "after_system_defined": [],
    }


@pytest.mark.asyncio
async def test_reorder_firewall_policies(local_settings, client):
    from src.tools.firewall_policies import reorder_firewall_policies

    body = {
        "orderedFirewallPolicyIds": {"beforeSystemDefined": ["b", "a"], "afterSystemDefined": ["c"]}
    }
    client.put = AsyncMock(return_value=body)
    cls, _ = _patched(client)
    try:
        result = await reorder_firewall_policies(
            "default",
            SRC_ZONE,
            DST_ZONE,
            local_settings,
            before_system_defined=["b", "a"],
            after_system_defined=["c"],
            confirm=True,
        )
    finally:
        cls.stop()

    client.put.assert_awaited_once_with(
        f"{BASE}/ordering",
        json_data=body,
        params={"sourceFirewallZoneId": SRC_ZONE, "destinationFirewallZoneId": DST_ZONE},
    )
    assert result["before_system_defined"] == ["b", "a"]
    assert result["after_system_defined"] == ["c"]


@pytest.mark.asyncio
async def test_reorder_firewall_policies_dry_run(local_settings):
    from src.tools.firewall_policies import reorder_firewall_policies

    with patch("src.tools.firewall_policies.UniFiClient") as cls:
        result = await reorder_firewall_policies(
            "default",
            SRC_ZONE,
            DST_ZONE,
            local_settings,
            before_system_defined=["a"],
            dry_run=True,
        )
    cls.assert_not_called()
    assert result == {
        "dry_run": True,
        "operation": "reorder_firewall_policies",
        "params": {"sourceFirewallZoneId": SRC_ZONE, "destinationFirewallZoneId": DST_ZONE},
        "payload": {
            "orderedFirewallPolicyIds": {"beforeSystemDefined": ["a"], "afterSystemDefined": []}
        },
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("confirm", [False, "false"])
async def test_reorder_firewall_policies_requires_confirm(local_settings, confirm):
    from src.tools.firewall_policies import reorder_firewall_policies

    with patch("src.tools.firewall_policies.UniFiClient") as cls:
        with pytest.raises(ValidationError):
            await reorder_firewall_policies(
                "default",
                SRC_ZONE,
                DST_ZONE,
                local_settings,
                before_system_defined=["a"],
                confirm=confirm,
            )
    cls.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("before", "after"),
    [([], []), (["a", "a"], []), (["a"], ["a"]), (None, None)],
)
async def test_reorder_firewall_policies_rejects_bad_lists(local_settings, before, after):
    from src.tools.firewall_policies import reorder_firewall_policies

    with patch("src.tools.firewall_policies.UniFiClient") as cls:
        with pytest.raises(ValidationError):
            await reorder_firewall_policies(
                "default",
                SRC_ZONE,
                DST_ZONE,
                local_settings,
                before_system_defined=before,
                after_system_defined=after,
                confirm=True,
            )
    cls.assert_not_called()


@pytest.mark.asyncio
async def test_reorder_requires_zone_ids(local_settings):
    from src.tools.firewall_policies import reorder_firewall_policies

    with pytest.raises(ValidationError):
        await reorder_firewall_policies(
            "default", " ", DST_ZONE, local_settings, before_system_defined=["a"], confirm=True
        )


@pytest.mark.asyncio
async def test_set_firewall_policy_logging(local_settings, client):
    from src.tools.firewall_policies import set_firewall_policy_logging

    client.patch = AsyncMock(return_value=dict(_POLICY, loggingEnabled=True))
    cls, _ = _patched(client)
    try:
        result = await set_firewall_policy_logging(
            "default", _POLICY["id"], True, local_settings, confirm=True
        )
    finally:
        cls.stop()

    client.patch.assert_awaited_once_with(
        f"{BASE}/{_POLICY['id']}", json_data={"loggingEnabled": True}
    )
    assert result["loggingEnabled"] is True


@pytest.mark.asyncio
async def test_set_firewall_policy_logging_dry_run_and_confirm(local_settings):
    from src.tools.firewall_policies import set_firewall_policy_logging

    with patch("src.tools.firewall_policies.UniFiClient") as cls:
        preview = await set_firewall_policy_logging(
            "default", "p1", False, local_settings, dry_run=True
        )
        with pytest.raises(ValidationError):
            await set_firewall_policy_logging("default", "p1", False, local_settings)
    cls.assert_not_called()
    assert preview["payload"] == {"loggingEnabled": False}
