"""Network data model."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Network(BaseModel):
    """UniFi network configuration."""

    id: str = Field(..., description="Network ID", alias="_id")
    name: str = Field(..., description="Network name")
    purpose: str = Field(..., description="Network purpose (corporate, guest, etc.)")

    # Network configuration
    vlan_enabled: bool | None = Field(None, description="VLAN assignment enabled")
    vlan_id: int | None = Field(None, description="VLAN ID number", alias="vlan")
    enabled: bool | None = Field(None, description="Whether network is enabled")

    # IP configuration
    ip_subnet: str | None = Field(None, description="IP subnet (CIDR notation)")
    networkgroup: str | None = Field(None, description="Network group")
    domain_name: str | None = Field(None, description="Domain name")

    # DHCP settings
    dhcpd_enabled: bool | None = Field(None, description="Whether DHCP is enabled")
    dhcpd_start: str | None = Field(None, description="DHCP range start")
    dhcpd_stop: str | None = Field(None, description="DHCP range end")
    dhcpd_leasetime: int | None = Field(None, description="DHCP lease time in seconds")
    dhcpd_dns_enabled: bool | None = Field(None, description="Whether DHCP DNS is enabled")
    dhcpd_dns_1: str | None = Field(None, description="Primary DNS server")
    dhcpd_dns_2: str | None = Field(None, description="Secondary DNS server")
    dhcpd_dns_3: str | None = Field(None, description="Tertiary DNS server")
    dhcpd_dns_4: str | None = Field(None, description="Quaternary DNS server")
    dhcpd_gateway_enabled: bool | None = Field(None, description="Whether DHCP gateway is enabled")
    dhcpd_gateway: str | None = Field(None, description="DHCP gateway IP")

    # IGMP settings
    igmp_snooping: bool | None = Field(None, description="IGMP snooping enabled")

    # IPv6
    ipv6_interface_type: str | None = Field(None, description="IPv6 interface type")
    ipv6_pd_start: str | None = Field(None, description="IPv6 prefix delegation start")
    ipv6_pd_stop: str | None = Field(None, description="IPv6 prefix delegation stop")
    ipv6_ra_enabled: bool | None = Field(None, description="IPv6 router advertisement enabled")
    ipv6_ra_priority: str | None = Field(None, description="IPv6 router advertisement priority")
    ipv6_pd_interface: str | None = Field(None, description="WAN that delegates the IPv6 prefix")
    ipv6_pd_prefixid: str | None = Field(None, description="IPv6 delegated prefix ID")
    ipv6_subnets: list[str] | None = Field(None, description="Static IPv6 subnets")
    ipv6_setting_preference: str | None = Field(None, description="IPv6 setting preference")
    dhcpdv6_enabled: bool | None = Field(None, description="DHCPv6 server enabled")
    dhcpdv6_start: str | None = Field(None, description="DHCPv6 range start")
    dhcpdv6_stop: str | None = Field(None, description="DHCPv6 range end")
    dhcpdv6_leasetime: int | None = Field(None, description="DHCPv6 lease time in seconds")
    dhcpdv6_dns_auto: bool | None = Field(None, description="DHCPv6 DNS servers set automatically")

    # Site association
    site_id: str | None = Field(None, description="Site ID")

    @field_validator("vlan_id", mode="before")
    @classmethod
    def coerce_empty_vlan_to_none(cls, v: Any) -> int | None:
        """Convert empty string VLAN IDs to None.

        The UniFi API returns vlan as an empty string ("") for WAN networks
        that don't have a VLAN ID. This validator converts that to None
        before Pydantic attempts integer coercion.

        Args:
            v: The vlan value from the API response

        Returns:
            None if v is an empty string, otherwise v as-is for Pydantic to coerce
        """
        if v == "":
            return None
        return v  # type: ignore[no-any-return]

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "_id": "507f191e810c19729de860ea",
                "name": "LAN",
                "purpose": "corporate",
                "vlan_enabled": True,
                "vlan": 1,
                "ip_subnet": "192.168.1.0/24",
                "dhcpd_enabled": True,
                "dhcpd_start": "192.168.2.100",
                "dhcpd_stop": "192.168.1.254",
            }
        },
    )
