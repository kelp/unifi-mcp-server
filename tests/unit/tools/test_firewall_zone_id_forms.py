"""Zone ID forms for v2 firewall policy tools.

Live (UCG Fiber, Network 10.6.106): list_firewall_zones returns integration
UUIDs, v2 policies carry Mongo ObjectIds, and the v2 zone list has ``_id`` and
``name`` but no ``external_id``. The tools must match the two zone lists by
name.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.config import Settings

IOT_UUID = "11111111-2222-4333-8444-555555555555"
GW_UUID = "66666666-7777-4888-9999-aaaaaaaaaaaa"
IOT_OID = "650000000000000000000002"  # pragma: allowlist secret
GW_OID = "650000000000000000000001"  # pragma: allowlist secret

V2_ZONES = [{"_id": IOT_OID, "name": "IoT"}, {"_id": GW_OID, "name": "Gateway"}]
INTEGRATION_ZONES = {
    "data": [
        {"id": IOT_UUID, "name": "IoT", "networkIds": []},
        {"id": GW_UUID, "name": "Gateway", "networkIds": []},
    ]
}
POLICIES = [
    {
        "_id": "p1",
        "name": "IoT to Gateway DNS",
        "enabled": True,
        "action": "ALLOW",
        "predefined": False,
        "index": 10000,
        "source": {"zone_id": IOT_OID, "matching_target": "ANY"},
        "destination": {"zone_id": GW_OID, "matching_target": "ANY"},
    },
    {
        "_id": "p2",
        "name": "Gateway to IoT",
        "enabled": True,
        "action": "BLOCK",
        "predefined": False,
        "index": 10001,
        "source": {"zone_id": GW_OID, "matching_target": "ANY"},
        "destination": {"zone_id": IOT_OID, "matching_target": "ANY"},
    },
]


@pytest.fixture
def local_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("UNIFI_API_KEY", "test-api-key")
    monkeypatch.setenv("UNIFI_API_TYPE", "local")
    monkeypatch.setenv("UNIFI_LOCAL_HOST", "192.0.2.1")
    return Settings()


@pytest.fixture(autouse=True)
def _clear_zone_cache():
    from src.tools import firewall_policies

    firewall_policies._zone_cache.clear()
    firewall_policies._zone_names.clear()
    yield
    firewall_policies._zone_cache.clear()
    firewall_policies._zone_names.clear()


def _client():
    async def get(path, params=None):
        if path.endswith("/firewall-policies"):
            return [dict(p) for p in POLICIES]
        if path.endswith("/v2/api/site/default/firewall/zone"):
            return V2_ZONES
        if path.endswith("/integration/v1/sites/site-uuid/firewall/zones"):
            return INTEGRATION_ZONES
        raise AssertionError(f"unexpected GET {path}")

    client = AsyncMock()
    client._site_uuid_to_name = {}
    client.is_authenticated = True
    client.resolve_site_id = AsyncMock(return_value="site-uuid")
    client.get = AsyncMock(side_effect=get)
    client.post = AsyncMock(return_value=dict(POLICIES[1]))
    return client


def _patched(client):
    cls = patch("src.tools.firewall_policies.UniFiClient")
    started = cls.start()
    started.return_value.__aenter__.return_value = client
    started.return_value.__aexit__.return_value = False
    return cls


@pytest.mark.asyncio
@pytest.mark.parametrize("source", [IOT_UUID, IOT_OID, "IoT", "iot"])
async def test_list_filter_accepts_uuid_objectid_and_name(local_settings, source):
    from src.tools.firewall_policies import list_firewall_policies

    cls = _patched(_client())
    try:
        result = await list_firewall_policies("default", local_settings, source_zone_id=source)
    finally:
        cls.stop()

    assert [p["name"] for p in result] == ["IoT to Gateway DNS"]


@pytest.mark.asyncio
async def test_list_adds_zone_names(local_settings):
    from src.tools.firewall_policies import list_firewall_policies

    cls = _patched(_client())
    try:
        result = await list_firewall_policies(
            "default", local_settings, destination_zone_id=GW_UUID
        )
    finally:
        cls.stop()

    assert len(result) == 1
    assert result[0]["source_zone_name"] == "IoT"
    assert result[0]["destination_zone_name"] == "Gateway"


@pytest.mark.asyncio
async def test_create_accepts_integration_uuid(local_settings):
    from src.tools.firewall_policies import create_firewall_policy

    client = _client()
    cls = _patched(client)
    try:
        await create_firewall_policy(
            name="Block IoT to Gateway",
            action="BLOCK",
            site_id="default",
            settings=local_settings,
            source_zone_id=IOT_UUID,
            destination_zone_id=GW_UUID,
            confirm=True,
        )
    finally:
        cls.stop()

    body = client.post.call_args[1]["json_data"]
    assert body["source"]["zone_id"] == IOT_OID
    assert body["destination"]["zone_id"] == GW_OID


@pytest.mark.asyncio
async def test_unknown_uuid_still_raises(local_settings):
    from src.tools.firewall_policies import list_firewall_policies

    cls = _patched(_client())
    try:
        with pytest.raises(ValueError, match="Could not resolve firewall zone"):
            await list_firewall_policies(
                "default",
                local_settings,
                source_zone_id="99999999-9999-9999-9999-999999999999",
            )
    finally:
        cls.stop()
