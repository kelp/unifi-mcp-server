"""Tests for DNS policy write tools (gap N6).

Routes: POST /v1/sites/{site}/dns/policies, PUT and DELETE
/v1/sites/{site}/dns/policies/{id} on the local integration API.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.config import Settings
from src.utils.exceptions import ValidationError

BASE = "/proxy/network/integration/v1/sites/site-uuid/dns/policies"
POLICY_ID = "44444444-4444-4444-4444-444444444444"

_A_RECORD = {
    "type": "A_RECORD",
    "id": POLICY_ID,
    "enabled": True,
    "domain": "nas.home.arpa",
    "ipv4Address": "192.0.2.10",
    "ttlSeconds": 300,
    "metadata": {"origin": "USER_DEFINED"},
}


@pytest.fixture
def local_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("UNIFI_API_KEY", "test-api-key")
    monkeypatch.setenv("UNIFI_API_TYPE", "local")
    monkeypatch.setenv("UNIFI_LOCAL_HOST", "192.0.2.1")
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
    cls = patch("src.tools.dns_management.UniFiClient")
    started = cls.start()
    started.return_value.__aenter__.return_value = client
    started.return_value.__aexit__.return_value = False
    return cls


@pytest.mark.asyncio
async def test_create_a_record(local_settings, client):
    from src.tools.dns_management import create_dns_policy

    client.post = AsyncMock(return_value=dict(_A_RECORD))
    cls = _patched(client)
    try:
        result = await create_dns_policy(
            "default",
            "A_RECORD",
            "nas.home.arpa",
            local_settings,
            ipv4_address="192.0.2.10",
            ttl_seconds=300,
            confirm=True,
        )
    finally:
        cls.stop()

    client.post.assert_awaited_once_with(
        BASE,
        json_data={
            "type": "A_RECORD",
            "enabled": True,
            "domain": "nas.home.arpa",
            "ipv4Address": "192.0.2.10",
            "ttlSeconds": 300,
        },
    )
    assert result["id"] == POLICY_ID


@pytest.mark.asyncio
async def test_create_srv_record_dry_run(local_settings):
    from src.tools.dns_management import create_dns_policy

    with patch("src.tools.dns_management.UniFiClient") as cls:
        result = await create_dns_policy(
            "default",
            "srv_record",
            "_sip._tcp.home.arpa",
            local_settings,
            service="_sip",
            protocol="_tcp",
            server_domain="pbx.home.arpa",
            port=5060,
            priority=10,
            weight=5,
            dry_run=True,
        )
    cls.assert_not_called()
    assert result == {
        "dry_run": True,
        "operation": "create_dns_policy",
        "payload": {
            "type": "SRV_RECORD",
            "enabled": True,
            "domain": "_sip._tcp.home.arpa",
            "service": "_sip",
            "protocol": "_tcp",
            "serverDomain": "pbx.home.arpa",
            "port": 5060,
            "priority": 10,
            "weight": 5,
        },
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("policy_type", "kwargs"),
    [
        ("A_RECORD", {}),  # missing ipv4_address
        ("CNAME_RECORD", {"ipv4_address": "192.0.2.1", "target_domain": "x.example"}),
        ("MX_RECORD", {"mail_server_domain": "mx.example"}),  # missing priority
        ("NS_RECORD", {"text": "x"}),  # unknown type
    ],
)
async def test_create_rejects_bad_fields(local_settings, policy_type, kwargs):
    from src.tools.dns_management import create_dns_policy

    with patch("src.tools.dns_management.UniFiClient") as cls:
        with pytest.raises(ValidationError):
            await create_dns_policy(
                "default", policy_type, "x.example", local_settings, confirm=True, **kwargs
            )
    cls.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("confirm", [False, "false"])
async def test_create_requires_confirm(local_settings, confirm):
    from src.tools.dns_management import create_dns_policy

    with patch("src.tools.dns_management.UniFiClient") as cls:
        with pytest.raises(ValidationError):
            await create_dns_policy(
                "default",
                "TXT_RECORD",
                "x.example",
                local_settings,
                text="v=spf1 -all",
                confirm=confirm,
            )
    cls.assert_not_called()


@pytest.mark.asyncio
async def test_create_refused_in_cloud(cloud_settings):
    from src.tools.dns_management import create_dns_policy

    with pytest.raises(NotImplementedError):
        await create_dns_policy(
            "default", "TXT_RECORD", "x.example", cloud_settings, text="t", confirm=True
        )


@pytest.mark.asyncio
async def test_update_merges_and_keeps_type(local_settings, client):
    from src.tools.dns_management import update_dns_policy

    client.get = AsyncMock(return_value=dict(_A_RECORD))
    client.put = AsyncMock(return_value=dict(_A_RECORD, ipv4Address="192.0.2.20"))
    cls = _patched(client)
    try:
        result = await update_dns_policy(
            "default", POLICY_ID, local_settings, ipv4_address="192.0.2.20", confirm=True
        )
    finally:
        cls.stop()

    client.get.assert_awaited_once_with(f"{BASE}/{POLICY_ID}")
    client.put.assert_awaited_once_with(
        f"{BASE}/{POLICY_ID}",
        json_data={
            "type": "A_RECORD",
            "enabled": True,
            "domain": "nas.home.arpa",
            "ipv4Address": "192.0.2.20",
            "ttlSeconds": 300,
        },
    )
    assert result["ipv4Address"] == "192.0.2.20"


@pytest.mark.asyncio
async def test_update_rejects_field_of_other_type(local_settings, client):
    from src.tools.dns_management import update_dns_policy

    client.get = AsyncMock(return_value=dict(_A_RECORD))
    client.put = AsyncMock()
    cls = _patched(client)
    try:
        with pytest.raises(ValidationError):
            await update_dns_policy(
                "default", POLICY_ID, local_settings, target_domain="x.example", confirm=True
            )
    finally:
        cls.stop()
    client.put.assert_not_called()


@pytest.mark.asyncio
async def test_update_dry_run_reads_but_does_not_write(local_settings, client):
    from src.tools.dns_management import update_dns_policy

    client.get = AsyncMock(return_value={"data": dict(_A_RECORD)})
    client.put = AsyncMock()
    cls = _patched(client)
    try:
        result = await update_dns_policy(
            "default", POLICY_ID, local_settings, enabled=False, dry_run=True
        )
    finally:
        cls.stop()

    client.put.assert_not_called()
    assert result["dry_run"] is True
    assert result["payload"]["enabled"] is False
    assert result["payload"]["ipv4Address"] == "192.0.2.10"


@pytest.mark.asyncio
async def test_update_requires_a_change(local_settings):
    from src.tools.dns_management import update_dns_policy

    with patch("src.tools.dns_management.UniFiClient") as cls:
        with pytest.raises(ValidationError):
            await update_dns_policy("default", POLICY_ID, local_settings, confirm=True)
    cls.assert_not_called()


@pytest.mark.asyncio
async def test_delete_dns_policy(local_settings, client):
    from src.tools.dns_management import delete_dns_policy

    client.delete = AsyncMock(return_value={})
    cls = _patched(client)
    try:
        result = await delete_dns_policy("default", POLICY_ID, local_settings, confirm=True)
    finally:
        cls.stop()

    client.delete.assert_awaited_once_with(f"{BASE}/{POLICY_ID}")
    assert result == {"success": True, "policy_id": POLICY_ID}


@pytest.mark.asyncio
async def test_delete_dns_policy_dry_run_and_confirm(local_settings):
    from src.tools.dns_management import delete_dns_policy

    with patch("src.tools.dns_management.UniFiClient") as cls:
        preview = await delete_dns_policy("default", POLICY_ID, local_settings, dry_run=True)
        with pytest.raises(ValidationError):
            await delete_dns_policy("default", POLICY_ID, local_settings)
    cls.assert_not_called()
    assert preview == {"dry_run": True, "operation": "delete_dns_policy", "policy_id": POLICY_ID}
