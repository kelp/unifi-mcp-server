# UniFi Network 10.6 UI Notes

Where settings are in the UniFi Network 10.6 UI, and how each one maps to
the controller API and to this server's tools. Many settings moved between
versions, so older guides often give the wrong path.

Observed on UniFi Network 10.6.106, UniFi OS 5.1.33, UCG Fiber, with the
zone-based firewall on.

Labels:

- **Confirmed**: seen in the UI or read from the controller on 10.6.106.
- **Unverified**: from third-party guides only. Check the path before you
  rely on it.

## Device SSH

| Item | Value |
|------|-------|
| UI | "Device SSH Settings" section, with the checkboxes "Inform Host Override" and "Device SSH Authentication" (confirmed). Guides put it under Devices > Device Updates and Settings (unverified). |
| Scope | Site-wide. If you check "Device SSH Authentication", SSH starts on every adopted device. |
| MCP tool | None. No tool reads or sets device SSH. |

Behavior seen with Device SSH Authentication off (confirmed):

- The gateway and the access points refuse connections on TCP port 22.
- Flex 2.5G switches (2.1.8) and UPS Tower (1.6.4) accept the TCP
  connection and then reset it before they send an SSH banner. No SSH
  session can start. `nc -z` reports these ports as open, so use an SSH
  handshake (`ssh -v`) to check.
- A U5G Backup (1.4.3) kept dropbear running, with password and public-key
  login, until a reboot. Force provision did not stop it.

## Network IPv6

| Item | Value |
|------|-------|
| UI | Settings > Networks > *network* > IPv6 (confirmed) |
| Fields | Interface Type (None, Prefix Delegation, Static), Prefix Delegation Interface, Prefix Delegation ID, Client Address Assignment (SLAAC, DHCPv6), Auto DNS Server, Router Advertisement (RA), RA Priority |
| API | Legacy `rest/networkconf`: `ipv6_interface_type`, `ipv6_pd_interface`, `ipv6_pd_auto_prefixid_enabled`, `ipv6_ra_enabled`, `ipv6_ra_priority`, `ipv6_client_address_assignment`, `dhcpdv6_*`. The live prefix is in `stat/device`, gateway `network_table[].ipv6_subnets`. |
| MCP tool | `get_network_details` and `list_vlans` drop most of these fields. `update_network` has no IPv6 arguments. |

Prefix Delegation ID is Auto only. The tooltip says manual prefix IDs come
in a future release (confirmed).

A network with Router Advertisement off gives clients no SLAAC address and
no IPv6 default route, even when it has a prefix.

## WAN IPv6

| Item | Value |
|------|-------|
| UI | WAN settings > IPv6 Configuration (confirmed) |
| Fields | Connection (Disabled, SLAAC, DHCPv6, Static), DHCPv6 Client Options, DHCPv6 CoS, Prefix Delegation Size (Auto or a number), Auto DNS Server |
| API | Legacy `rest/networkconf` WAN entries: `wan_type_v6`, `ipv6_wan_delegation_type`, `wan_dhcpv6_pd_size_auto`, `wan_dhcpv6_pd_size`, `wan_ipv6_dns_preference` |
| MCP tool | None. |

### AT&T gateway in IP passthrough

The AT&T gateway gives each router one /64, so only one network gets an
IPv6 prefix. Set Prefix Delegation Size to `64`. A larger size (60 or 56)
is reported not to work with AT&T. To give a prefix to a different network,
set the current network to None and the new network to Prefix Delegation.
The gateway can take some time to request the prefix again. Saving the WAN
settings restarts the DHCPv6 client.

## mDNS proxy

| Item | Value |
|------|-------|
| UI | "Gateway mDNS Proxy" under Settings > Networks, modes All, Auto, Custom, Off (unverified). Each network also has a Multicast DNS toggle. |
| API | Legacy `rest/setting`, key `mdns`: `mode`, `enabled_for`, `enabled_for_network_ids`, `predefined_services`, `custom_services` (confirmed). Per network: `mdns_enabled` in `rest/networkconf` (confirmed). |
| MCP tool | None. |

A community report on 10.4.57 says that with the proxy Off or Custom, the
gateway still sends mDNS onto excluded VLANs.

## Gaps in this server

Each setting above has no MCP read or write tool, or a tool that drops its
fields. Read these settings through the legacy routes listed above until
the tools cover them.
