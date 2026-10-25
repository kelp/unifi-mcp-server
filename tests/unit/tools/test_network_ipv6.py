"""IPv6 fields on networks (gap L1).

The Network model dropped the controller's IPv6 keys, and create_network and
update_network had no IPv6 arguments. Field names are the legacy
``rest/networkconf`` names.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.tools.network_config as nc_module
from src.models.network import Network
from src.tools.network_config import create_network, update_network
from src.utils.exceptions import ValidationError

_IPV6_FIELDS = {
    "ipv6_interface_type": "pd",
    "ipv6_ra_enabled": True,
    "ipv6_ra_priority": "high",
    "ipv6_pd_interface": "wan",
    "ipv6_pd_prefixid": "1",
    "ipv6_pd_start": "::2",
    "ipv6_pd_stop": "::7d1",
    "ipv6_subnets": ["2001:db8:1::1/64"],
    "ipv6_setting_preference": "auto",
    "dhcpdv6_enabled": True,
    "dhcpdv6_start": "::2",
    "dhcpdv6_stop": "::7d1",
    "dhcpdv6_leasetime": 86400,
    "dhcpdv6_dns_auto": True,
}


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.log_level = "INFO"
    return settings


def _client(existing: dict) -> MagicMock:
    client = MagicMock()
    client.authenticate = AsyncMock()
    client.get = AsyncMock(return_value={"data": [existing]})
    client.put = AsyncMock(return_value={"data": [existing]})
    client.post = AsyncMock(return_value={"data": [existing]})
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


def test_network_model_keeps_ipv6_fields():
    record = {"_id": "n1", "name": "LAN", "purpose": "corporate", **_IPV6_FIELDS}
    dumped = Network.model_validate(record).model_dump()
    for key, value in _IPV6_FIELDS.items():
        assert dumped[key] == value, key


@pytest.mark.asyncio
async def test_update_network_sets_ipv6_fields(mock_settings):
    existing = {"_id": "n1", "name": "LAN", "purpose": "corporate", "ipv6_interface_type": "none"}
    client = _client(existing)

    with patch.object(nc_module, "UniFiClient", return_value=client):
        await update_network(
            site_id="default",
            network_id="n1",
            settings=mock_settings,
            ipv6_interface_type="pd",
            ipv6_pd_interface="wan",
            ipv6_pd_prefixid="1",
            ipv6_ra_enabled=True,
            dhcpv6_enabled=True,
            dhcpv6_start="::2",
            dhcpv6_stop="::7d1",
            confirm=True,
        )

    body = client.put.call_args[1]["json_data"]
    assert body["name"] == "LAN"
    assert body["ipv6_interface_type"] == "pd"
    assert body["ipv6_pd_interface"] == "wan"
    assert body["ipv6_pd_prefixid"] == "1"
    assert body["ipv6_ra_enabled"] is True
    assert body["dhcpdv6_enabled"] is True
    assert body["dhcpdv6_start"] == "::2"
    assert body["dhcpdv6_stop"] == "::7d1"


@pytest.mark.asyncio
async def test_update_network_leaves_ipv6_alone_by_default(mock_settings):
    existing = {"_id": "n1", "name": "LAN", "purpose": "corporate", **_IPV6_FIELDS}
    client = _client(existing)

    with patch.object(nc_module, "UniFiClient", return_value=client):
        await update_network(
            site_id="default", network_id="n1", settings=mock_settings, name="LAN2", confirm=True
        )

    body = client.put.call_args[1]["json_data"]
    for key, value in _IPV6_FIELDS.items():
        assert body[key] == value, key


@pytest.mark.asyncio
async def test_create_network_sets_ipv6_fields(mock_settings):
    client = _client({"_id": "n2", "name": "IoT", "purpose": "corporate"})

    with patch.object(nc_module, "UniFiClient", return_value=client):
        await create_network(
            site_id="default",
            name="IoT",
            vlan_id=30,
            subnet="192.0.2.0/24",
            settings=mock_settings,
            ipv6_interface_type="pd",
            ipv6_pd_interface="wan",
            ipv6_ra_enabled=True,
            confirm=True,
        )

    body = client.post.call_args[1]["json_data"]
    assert body["ipv6_interface_type"] == "pd"
    assert body["ipv6_pd_interface"] == "wan"
    assert body["ipv6_ra_enabled"] is True
    assert "dhcpdv6_enabled" not in body


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", ["create", "update"])
async def test_invalid_ipv6_interface_type(mock_settings, tool):
    with patch.object(nc_module, "UniFiClient") as cls:
        with pytest.raises(ValidationError):
            if tool == "create":
                await create_network(
                    site_id="default",
                    name="IoT",
                    vlan_id=30,
                    subnet="192.0.2.0/24",
                    settings=mock_settings,
                    ipv6_interface_type="dhcpv6",
                    confirm=True,
                )
            else:
                await update_network(
                    site_id="default",
                    network_id="n1",
                    settings=mock_settings,
                    ipv6_interface_type="dhcpv6",
                    confirm=True,
                )
    cls.assert_not_called()
