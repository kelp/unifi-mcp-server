"""DNS management tools (WAN DNS, DNS filtering).

Manages WAN upstream DNS servers via ``/rest/networkconf/{wan_id}`` and
per-network DNS filtering (CyberSecure DNS-level) via the ``[ips]``
settings endpoint. Both are on the legacy V1 internal API, local-only.

**DoT (DNS-over-TLS)** configuration is NOT exposed via REST API on
current UDM firmware (10.2.x). The ``rest/setting/connectivity`` endpoint
has no DoT-related fields. DoT must be configured in the UI for now.
"""

from typing import Any

from ..api.client import UniFiClient
from ..config import APIType, Settings
from ..utils import APIError, get_logger, log_audit, sanitize_log_message, validate_site_id
from ..utils.exceptions import ValidationError
from ..utils.tool_kind import read_tool, write_tool
from ..utils.validators import coerce_bool, validate_confirmation

logger = get_logger(__name__)


def _ensure_local_api(settings: Settings) -> None:
    if settings.api_type != APIType.LOCAL:
        raise NotImplementedError("DNS management tools require UNIFI_API_TYPE='local'.")


def _unwrap(response: Any) -> list[dict[str, Any]]:
    if isinstance(response, list):
        return [i for i in response if isinstance(i, dict)]
    if isinstance(response, dict):
        inner = response.get("data")
        if isinstance(inner, list):
            return [i for i in inner if isinstance(i, dict)]
        if isinstance(inner, dict):
            return [inner]
    return []


# --------------------------------------------------------------------------- #
# WAN DNS                                                                     #
# --------------------------------------------------------------------------- #


@read_tool
async def list_wan_dns(
    site_id: str,
    settings: Settings,
) -> list[dict[str, Any]]:
    """List WAN connections with their DNS settings.

    Returns each WAN interface's name, ID, current DNS servers, and
    dns_preference mode (``auto`` or ``manual``).
    """
    site_id = validate_site_id(site_id)
    _ensure_local_api(settings)

    async with UniFiClient(settings) as client:
        logger.info(sanitize_log_message(f"Listing WAN DNS for site {site_id}"))
        if not client.is_authenticated:
            await client.authenticate()

        try:
            response = await client.get(f"/ea/sites/{site_id}/rest/networkconf")
        except APIError:
            logger.exception(sanitize_log_message(f"Failed to list networks for site {site_id}"))
            raise

        items = _unwrap(response)
        wans = [n for n in items if n.get("purpose") == "wan"]

        return [
            {
                "id": w.get("_id"),
                "name": w.get("name"),
                "wan_dns1": w.get("wan_dns1"),
                "wan_dns2": w.get("wan_dns2"),
                "wan_dns_preference": w.get("wan_dns_preference", "auto"),
                "wan_type": w.get("wan_type"),
                "wan_networkgroup": w.get("wan_networkgroup"),
            }
            for w in wans
        ]


@write_tool
async def update_wan_dns(
    wan_network_id: str,
    site_id: str,
    settings: Settings,
    dns1: str | None = None,
    dns2: str | None = None,
    dns_preference: str | None = None,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Update DNS settings on a WAN interface.

    Args:
        wan_network_id: The WAN network's ``_id`` (from ``list_wan_dns``)
        site_id: Site identifier
        settings: Application settings (must be local)
        dns1: Primary DNS server IP (e.g. ``"172.64.36.1"``)
        dns2: Secondary DNS server IP
        dns_preference: ``"manual"`` to use dns1/dns2, ``"auto"`` for
            DHCP-provided DNS
        confirm: REQUIRED True
        dry_run: Preview without applying
    """
    site_id = validate_site_id(site_id)
    _ensure_local_api(settings)

    confirm_bool = coerce_bool(confirm)
    dry_run_bool = coerce_bool(dry_run)
    if not dry_run_bool and not confirm_bool:
        raise ValueError(
            "This operation requires confirm=True to execute. "
            "Use dry_run=True to preview changes first."
        )

    overrides: dict[str, Any] = {}
    if dns1 is not None:
        overrides["wan_dns1"] = dns1
    if dns2 is not None:
        overrides["wan_dns2"] = dns2
    if dns_preference is not None:
        if dns_preference not in ("auto", "manual"):
            raise ValueError("dns_preference must be 'auto' or 'manual'")
        overrides["wan_dns_preference"] = dns_preference

    # Auto-set to manual when specific DNS servers are provided
    if (dns1 is not None or dns2 is not None) and dns_preference is None:
        overrides["wan_dns_preference"] = "manual"

    if dry_run_bool:
        logger.info(sanitize_log_message(f"DRY RUN: Would update WAN DNS on {wan_network_id}"))
        return {"status": "dry_run", "wan_network_id": wan_network_id, "changes": overrides}

    async with UniFiClient(settings) as client:
        logger.info(
            sanitize_log_message(f"Updating WAN DNS on {wan_network_id} for site {site_id}")
        )
        if not client.is_authenticated:
            await client.authenticate()

        endpoint = f"/ea/sites/{site_id}/rest/networkconf/{wan_network_id}"

        try:
            response = await client.put(endpoint, json_data=overrides)
        except APIError:
            logger.exception(sanitize_log_message(f"Failed to update WAN DNS on {wan_network_id}"))
            raise

        items = _unwrap(response)
        data = items[0] if items else {}

        log_audit(
            operation="update_wan_dns",
            parameters={"site_id": site_id, "wan_network_id": wan_network_id, **overrides},
            result="success",
            site_id=site_id,
        )

        return {
            "id": data.get("_id"),
            "name": data.get("name"),
            "wan_dns1": data.get("wan_dns1"),
            "wan_dns2": data.get("wan_dns2"),
            "wan_dns_preference": data.get("wan_dns_preference"),
        }


# --------------------------------------------------------------------------- #
# DNS Filtering (CyberSecure DNS-level, per-network)                          #
# --------------------------------------------------------------------------- #


@read_tool
async def get_dns_filter_settings(
    site_id: str,
    settings: Settings,
) -> dict[str, Any]:
    """Get DNS filtering settings (CyberSecure DNS-level).

    Returns the global ``dns_filtering`` toggle and the per-network
    ``dns_filters`` list from the ``[ips]`` settings.
    """
    site_id = validate_site_id(site_id)
    _ensure_local_api(settings)

    async with UniFiClient(settings) as client:
        logger.info(sanitize_log_message(f"Getting DNS filter settings for site {site_id}"))
        if not client.is_authenticated:
            await client.authenticate()

        try:
            response = await client.get(f"/ea/sites/{site_id}/get/setting/ips")
        except APIError:
            logger.exception(sanitize_log_message("Failed to get DNS filter settings"))
            raise

        items = _unwrap(response)
        if not items:
            return {"dns_filtering": False, "dns_filters": []}

        ips_settings = items[0]
        return {
            "id": ips_settings.get("_id"),
            "dns_filtering": ips_settings.get("dns_filtering", False),
            "dns_filters": ips_settings.get("dns_filters", []),
        }


@write_tool
async def update_dns_filter(
    site_id: str,
    settings: Settings,
    network_id: str | None = None,
    dns_filtering: bool | None = None,
    filter_level: str | None = None,
    blocked_sites: list[str] | None = None,
    allowed_sites: list[str] | None = None,
    blocked_tld: list[str] | None = None,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Update DNS filtering settings.

    Can toggle the global ``dns_filtering`` switch and/or update a specific
    network's DNS filter configuration.

    Args:
        site_id: Site identifier
        settings: Application settings (must be local)
        network_id: Target a specific network's DNS filter entry. Required
            when updating per-network settings (filter_level, blocked_sites,
            etc.).
        dns_filtering: Toggle the global DNS filtering feature on/off
        filter_level: DNS filter level for the specified network. Common
            values: ``"none"``, ``"family"``, ``"work"``, ``"custom"``
        blocked_sites: Replace the blocked-sites list for this network
        allowed_sites: Replace the allowed-sites list
        blocked_tld: Replace the blocked TLD list
        confirm: REQUIRED True
        dry_run: Preview without applying
    """
    site_id = validate_site_id(site_id)
    _ensure_local_api(settings)

    confirm_bool = coerce_bool(confirm)
    dry_run_bool = coerce_bool(dry_run)
    if not dry_run_bool and not confirm_bool:
        raise ValueError(
            "This operation requires confirm=True to execute. "
            "Use dry_run=True to preview changes first."
        )

    async with UniFiClient(settings) as client:
        logger.info(sanitize_log_message(f"Updating DNS filter settings for site {site_id}"))
        if not client.is_authenticated:
            await client.authenticate()

        # Fetch current IPS settings
        try:
            response = await client.get(f"/ea/sites/{site_id}/get/setting/ips")
        except APIError:
            logger.exception(sanitize_log_message("Failed to get current DNS filter settings"))
            raise

        items = _unwrap(response)
        if not items:
            raise APIError("IPS settings not found")
        current = items[0]
        settings_id = current.get("_id")

        # Build the update
        update_payload: dict[str, Any] = {}

        if dns_filtering is not None:
            update_payload["dns_filtering"] = dns_filtering

        if network_id is not None and (
            filter_level is not None
            or blocked_sites is not None
            or allowed_sites is not None
            or blocked_tld is not None
        ):
            # Update a specific network's entry in dns_filters
            dns_filters = list(current.get("dns_filters", []))
            target_entry = None
            for entry in dns_filters:
                if isinstance(entry, dict) and entry.get("network_id") == network_id:
                    target_entry = entry
                    break

            if target_entry is None:
                # Create a new entry for this network
                target_entry = {
                    "network_id": network_id,
                    "filter": "none",
                    "blocked_tld": [],
                    "blocked_sites": [],
                    "allowed_sites": [],
                    "name": "",
                    "description": "",
                    "version": "v4",
                }
                dns_filters.append(target_entry)

            if filter_level is not None:
                target_entry["filter"] = filter_level
            if blocked_sites is not None:
                target_entry["blocked_sites"] = list(blocked_sites)
            if allowed_sites is not None:
                target_entry["allowed_sites"] = list(allowed_sites)
            if blocked_tld is not None:
                target_entry["blocked_tld"] = list(blocked_tld)

            update_payload["dns_filters"] = dns_filters

        if dry_run_bool:
            logger.info(sanitize_log_message("DRY RUN: Would update DNS filter settings"))
            return {
                "status": "dry_run",
                "settings_id": settings_id,
                "changes": update_payload,
            }

        try:
            put_response = await client.put(
                f"/ea/sites/{site_id}/set/setting/ips/{settings_id}",
                json_data=update_payload,
            )
        except APIError:
            logger.exception(sanitize_log_message("Failed to update DNS filter settings"))
            raise

        put_items = _unwrap(put_response)
        result = put_items[0] if put_items else {}

        log_audit(
            operation="update_dns_filter",
            parameters={"site_id": site_id, **update_payload},
            result="success",
            site_id=site_id,
        )

        return {
            "id": result.get("_id"),
            "dns_filtering": result.get("dns_filtering"),
            "dns_filters": result.get("dns_filters", []),
        }


# --------------------------------------------------------------------------- #
# DNS policies (integration API, gap N6)                                      #
# --------------------------------------------------------------------------- #

# Tool argument -> integration field name.
_DNS_FIELD_NAMES = {
    "ipv4_address": "ipv4Address",
    "ipv6_address": "ipv6Address",
    "target_domain": "targetDomain",
    "ip_address": "ipAddress",
    "mail_server_domain": "mailServerDomain",
    "priority": "priority",
    "port": "port",
    "protocol": "protocol",
    "server_domain": "serverDomain",
    "service": "service",
    "weight": "weight",
    "text": "text",
    "ttl_seconds": "ttlSeconds",
}

# Per policy type: (fields required on create, optional fields).
_DNS_POLICY_TYPES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "A_RECORD": (("ipv4Address",), ("ttlSeconds",)),
    "AAAA_RECORD": (("ipv6Address",), ("ttlSeconds",)),
    "CNAME_RECORD": (("targetDomain",), ("ttlSeconds",)),
    "FORWARD_DOMAIN": (("ipAddress",), ()),
    "MX_RECORD": (("mailServerDomain", "priority"), ()),
    "SRV_RECORD": (("service", "protocol", "serverDomain", "port", "priority", "weight"), ()),
    "TXT_RECORD": (("text",), ()),
}


def _dns_policies_path(settings: Settings, site_uuid: str, suffix: str = "") -> str:
    return settings.get_integration_path(f"sites/{site_uuid}/dns/policies{suffix}")


def _dns_type_fields(policy_type: str, values: dict[str, Any], require: bool) -> dict[str, Any]:
    """Map tool arguments to integration fields and check them against the type."""
    required, optional = _DNS_POLICY_TYPES[policy_type]
    given = {_DNS_FIELD_NAMES[k]: v for k, v in values.items() if v is not None}
    foreign = sorted(set(given) - set(required) - set(optional))
    if foreign:
        raise ValidationError(f"{policy_type} does not take: {', '.join(foreign)}")
    if require:
        missing = [f for f in required if f not in given]
        if missing:
            raise ValidationError(f"{policy_type} requires: {', '.join(missing)}")
    return given


def _dns_record(response: Any) -> dict[str, Any]:
    if isinstance(response, dict) and isinstance(response.get("data"), dict):
        return dict(response["data"])
    return dict(response) if isinstance(response, dict) else {}


@write_tool
async def create_dns_policy(
    site_id: str,
    policy_type: str,
    domain: str,
    settings: Settings,
    enabled: bool = True,
    ipv4_address: str | None = None,
    ipv6_address: str | None = None,
    target_domain: str | None = None,
    ip_address: str | None = None,
    mail_server_domain: str | None = None,
    priority: int | None = None,
    port: int | None = None,
    protocol: str | None = None,
    server_domain: str | None = None,
    service: str | None = None,
    weight: int | None = None,
    text: str | None = None,
    ttl_seconds: int | None = None,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Create a local DNS record or forward rule (integration DNS policy).

    Fields per ``policy_type``:

    - ``A_RECORD``: ipv4_address, optional ttl_seconds
    - ``AAAA_RECORD``: ipv6_address, optional ttl_seconds
    - ``CNAME_RECORD``: target_domain, optional ttl_seconds
    - ``FORWARD_DOMAIN``: ip_address (DNS server that gets queries for domain)
    - ``MX_RECORD``: mail_server_domain, priority (lower is preferred)
    - ``SRV_RECORD``: service, protocol, server_domain, port, priority, weight
    - ``TXT_RECORD``: text

    Args:
        site_id: Site identifier
        policy_type: One of the types above (case-insensitive)
        domain: Domain the policy answers for
        settings: Application settings (must be local)
        enabled: Turn the policy on (default True)
        ipv4_address: A_RECORD address
        ipv6_address: AAAA_RECORD address
        target_domain: CNAME_RECORD target
        ip_address: FORWARD_DOMAIN DNS server address
        mail_server_domain: MX_RECORD mail server
        priority: MX_RECORD or SRV_RECORD priority (lower is preferred)
        port: SRV_RECORD port
        protocol: SRV_RECORD protocol, e.g. ``_tcp``
        server_domain: SRV_RECORD target host
        service: SRV_RECORD service, e.g. ``_sip``
        weight: SRV_RECORD weight
        text: TXT_RECORD value
        ttl_seconds: Time to live for A, AAAA and CNAME records
        confirm: Must be true to apply (required unless dry_run)
        dry_run: Preview the request without sending it

    Returns:
        The created policy, with its integration UUID in ``id``
    """
    validate_confirmation(confirm, "create DNS policy", dry_run)
    _ensure_local_api(settings)
    site_id = validate_site_id(site_id)
    kind = (policy_type or "").strip().upper()
    if kind not in _DNS_POLICY_TYPES:
        raise ValidationError(f"policy_type must be one of: {', '.join(_DNS_POLICY_TYPES)}")
    domain = (domain or "").strip()
    if not domain:
        raise ValidationError("domain is required")

    fields = _dns_type_fields(
        kind,
        {
            "ipv4_address": ipv4_address,
            "ipv6_address": ipv6_address,
            "target_domain": target_domain,
            "ip_address": ip_address,
            "mail_server_domain": mail_server_domain,
            "priority": priority,
            "port": port,
            "protocol": protocol,
            "server_domain": server_domain,
            "service": service,
            "weight": weight,
            "text": text,
            "ttl_seconds": ttl_seconds,
        },
        require=True,
    )
    payload = {"type": kind, "enabled": coerce_bool(enabled), "domain": domain, **fields}
    if coerce_bool(dry_run):
        return {"dry_run": True, "operation": "create_dns_policy", "payload": payload}

    async with UniFiClient(settings) as client:
        if not client.is_authenticated:
            await client.authenticate()
        site_uuid = await client.resolve_site_id(site_id)
        response = await client.post(_dns_policies_path(settings, site_uuid), json_data=payload)

    logger.info(sanitize_log_message(f"Created {kind} DNS policy for {domain} on site {site_id}"))
    return _dns_record(response)


@write_tool
async def update_dns_policy(
    site_id: str,
    policy_id: str,
    settings: Settings,
    enabled: bool | None = None,
    domain: str | None = None,
    ipv4_address: str | None = None,
    ipv6_address: str | None = None,
    target_domain: str | None = None,
    ip_address: str | None = None,
    mail_server_domain: str | None = None,
    priority: int | None = None,
    port: int | None = None,
    protocol: str | None = None,
    server_domain: str | None = None,
    service: str | None = None,
    weight: int | None = None,
    text: str | None = None,
    ttl_seconds: int | None = None,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Update a DNS policy. Reads the policy, merges the changes, PUTs it back.

    The policy type cannot change; delete and create to change it. Pass only
    the fields of the policy's type (see create_dns_policy).

    Args:
        site_id: Site identifier
        policy_id: Integration policy UUID (from list_integration_dns_policies)
        settings: Application settings (must be local)
        enabled: Turn the policy on or off
        domain: New domain
        ipv4_address: A_RECORD address
        ipv6_address: AAAA_RECORD address
        target_domain: CNAME_RECORD target
        ip_address: FORWARD_DOMAIN DNS server address
        mail_server_domain: MX_RECORD mail server
        priority: MX_RECORD or SRV_RECORD priority (lower is preferred)
        port: SRV_RECORD port
        protocol: SRV_RECORD protocol, e.g. ``_tcp``
        server_domain: SRV_RECORD target host
        service: SRV_RECORD service, e.g. ``_sip``
        weight: SRV_RECORD weight
        text: TXT_RECORD value
        ttl_seconds: Time to live for A, AAAA and CNAME records
        confirm: Must be true to apply (required unless dry_run)
        dry_run: Preview the merged policy without writing it

    Returns:
        The updated policy
    """
    validate_confirmation(confirm, "update DNS policy", dry_run)
    _ensure_local_api(settings)
    site_id = validate_site_id(site_id)
    policy_id = (policy_id or "").strip()
    if not policy_id:
        raise ValidationError("policy_id is required")

    values = {
        "ipv4_address": ipv4_address,
        "ipv6_address": ipv6_address,
        "target_domain": target_domain,
        "ip_address": ip_address,
        "mail_server_domain": mail_server_domain,
        "priority": priority,
        "port": port,
        "protocol": protocol,
        "server_domain": server_domain,
        "service": service,
        "weight": weight,
        "text": text,
        "ttl_seconds": ttl_seconds,
    }
    if enabled is None and domain is None and all(v is None for v in values.values()):
        raise ValidationError("Pass at least one field to change")

    async with UniFiClient(settings) as client:
        if not client.is_authenticated:
            await client.authenticate()
        site_uuid = await client.resolve_site_id(site_id)
        path = _dns_policies_path(settings, site_uuid, f"/{policy_id}")
        current = _dns_record(await client.get(path))
        kind = str(current.get("type", "")).upper()
        if kind not in _DNS_POLICY_TYPES:
            raise ValidationError(f"Policy {policy_id} has unsupported type {kind!r}")

        changes = _dns_type_fields(kind, values, require=False)
        required, optional = _DNS_POLICY_TYPES[kind]
        payload: dict[str, Any] = {"type": kind, "enabled": current.get("enabled", True)}
        if current.get("domain") is not None:
            payload["domain"] = current["domain"]
        for field in required + optional:
            if field in current:
                payload[field] = current[field]
        payload.update(changes)
        if enabled is not None:
            payload["enabled"] = coerce_bool(enabled)
        if domain is not None:
            payload["domain"] = domain.strip()

        if coerce_bool(dry_run):
            return {
                "dry_run": True,
                "operation": "update_dns_policy",
                "policy_id": policy_id,
                "payload": payload,
            }
        response = await client.put(path, json_data=payload)

    logger.info(sanitize_log_message(f"Updated DNS policy {policy_id} on site {site_id}"))
    return _dns_record(response)


@write_tool
async def delete_dns_policy(
    site_id: str,
    policy_id: str,
    settings: Settings,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Delete a DNS policy (local DNS record or forward rule).

    Args:
        site_id: Site identifier
        policy_id: Integration policy UUID (from list_integration_dns_policies)
        settings: Application settings (must be local)
        confirm: Must be true to apply (required unless dry_run)
        dry_run: Preview without deleting

    Returns:
        {"success": True, "policy_id": ...}
    """
    validate_confirmation(confirm, "delete DNS policy", dry_run)
    _ensure_local_api(settings)
    site_id = validate_site_id(site_id)
    policy_id = (policy_id or "").strip()
    if not policy_id:
        raise ValidationError("policy_id is required")
    if coerce_bool(dry_run):
        return {"dry_run": True, "operation": "delete_dns_policy", "policy_id": policy_id}

    async with UniFiClient(settings) as client:
        if not client.is_authenticated:
            await client.authenticate()
        site_uuid = await client.resolve_site_id(site_id)
        await client.delete(_dns_policies_path(settings, site_uuid, f"/{policy_id}"))

    logger.info(sanitize_log_message(f"Deleted DNS policy {policy_id} on site {site_id}"))
    return {"success": True, "policy_id": policy_id}
