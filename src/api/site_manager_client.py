"""Site Manager API client for multi-site management."""

from typing import Any, cast

import httpx

from ..config import Settings
from ..utils import APIError, AuthenticationError, NetworkError, ResourceNotFoundError, get_logger

logger = get_logger(__name__)

#: A decoded JSON reply: most Site Manager endpoints answer with an object, but
#: endpoints reached through the Cloud Connector proxy can answer with an array.
JSONBody = dict[str, Any] | list[Any]


class SiteManagerClient:
    """Client for UniFi Site Manager API (api.ui.com/v1/)."""

    def __init__(self, settings: Settings) -> None:
        """Initialize Site Manager API client.

        Args:
            settings: Application settings
        """
        self.settings = settings
        self.logger = get_logger(__name__, settings.log_level)

        # Site Manager API base URL
        base_url = "https://api.ui.com/v1/"

        # Initialize HTTP client
        self.client = httpx.AsyncClient(
            base_url=base_url,
            headers=settings.get_headers(),
            timeout=settings.request_timeout,
            verify=True,  # Always verify SSL for Site Manager API
        )

        self._authenticated = False

    async def __aenter__(self) -> "SiteManagerClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()

    @property
    def is_authenticated(self) -> bool:
        """Check if client is authenticated.

        Returns:
            True if authenticated, False otherwise
        """
        return self._authenticated

    async def authenticate(self) -> None:
        """Authenticate with the Site Manager API.

        Raises:
            AuthenticationError: If authentication fails
        """
        try:
            # Test authentication with sites endpoint (relative to base_url /v1/)
            response = await self.client.get("sites")
            if response.status_code == 200:
                self._authenticated = True
                self.logger.info("Successfully authenticated with Site Manager API")
            else:
                raise AuthenticationError(f"Authentication failed: {response.status_code}")
        except Exception as e:
            self.logger.error(f"Site Manager authentication failed: {e}")
            raise AuthenticationError(f"Failed to authenticate with Site Manager API: {e}") from e

    async def get(self, endpoint: str, params: dict[str, Any] | None = None) -> JSONBody:
        """Make a GET request to Site Manager API.

        Args:
            endpoint: API endpoint path (without /v1/ prefix)
            params: Query parameters

        Returns:
            The decoded JSON reply: an object, or an array for endpoints that
            answer with one (many Cloud Connector proxy paths do)

        Raises:
            APIError: If API returns an error
            AuthenticationError: If authentication fails
        """
        if not self._authenticated:
            await self.authenticate()

        try:
            # base_url already includes /v1/ - pass endpoint as relative path
            endpoint = endpoint.lstrip("/")

            response = await self.client.get(endpoint, params=params)
            response.raise_for_status()

            return cast(JSONBody, response.json())

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("Site Manager API authentication failed") from e
            elif e.response.status_code == 404:
                raise ResourceNotFoundError("resource", endpoint) from e
            else:
                raise APIError(
                    message=f"Site Manager API error: {e.response.text}",
                    status_code=e.response.status_code,
                ) from e
        except httpx.NetworkError as e:
            raise NetworkError(f"Network communication failed: {e}") from e
        except Exception as e:
            self.logger.error(f"Unexpected error in Site Manager API request: {e}")
            raise APIError(f"Unexpected error: {e}") from e

    async def _mutate(
        self,
        method: str,
        endpoint: str,
        json_data: dict[str, Any] | None = None,
    ) -> JSONBody:
        """Make a mutating (POST/PUT/PATCH/DELETE) request to Site Manager API.

        Args:
            method: HTTP method (post, put, patch, delete)
            endpoint: API endpoint path (without /v1/ prefix)
            json_data: Optional request body

        Returns:
            The decoded JSON reply: an object, or an array for endpoints that
            answer with one (many Cloud Connector proxy paths do)

        Raises:
            APIError: If API returns an error
            AuthenticationError: If authentication fails
        """
        if not self._authenticated:
            await self.authenticate()

        try:
            endpoint = endpoint.lstrip("/")
            http_method = getattr(self.client, method)
            if json_data is not None:
                response = await http_method(endpoint, json=json_data)
            else:
                response = await http_method(endpoint)
            response.raise_for_status()

            if response.content:
                return cast(JSONBody, response.json())
            return {}

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("Site Manager API authentication failed") from e
            elif e.response.status_code == 404:
                raise ResourceNotFoundError("resource", endpoint) from e
            else:
                raise APIError(
                    message=f"Site Manager API error: {e.response.text}",
                    status_code=e.response.status_code,
                ) from e
        except httpx.NetworkError as e:
            raise NetworkError(f"Network communication failed: {e}") from e
        except Exception as e:
            self.logger.error(f"Unexpected error in Site Manager API request: {e}")
            raise APIError(f"Unexpected error: {e}") from e

    async def post(self, endpoint: str, json_data: dict[str, Any] | None = None) -> JSONBody:
        """Make a POST request to Site Manager API."""
        return await self._mutate("post", endpoint, json_data)

    async def put(self, endpoint: str, json_data: dict[str, Any] | None = None) -> JSONBody:
        """Make a PUT request to Site Manager API."""
        return await self._mutate("put", endpoint, json_data)

    async def patch(self, endpoint: str, json_data: dict[str, Any] | None = None) -> JSONBody:
        """Make a PATCH request to Site Manager API."""
        return await self._mutate("patch", endpoint, json_data)

    async def delete(self, endpoint: str) -> JSONBody:
        """Make a DELETE request to Site Manager API."""
        return await self._mutate("delete", endpoint)

    async def _get_object(self, endpoint: str, params: dict[str, Any] | None = None) -> JSONBody:
        """GET an endpoint documented to answer with a JSON object.

        Some deployments answer these endpoints (``hosts``, ``vantage-points``
        and others) with a bare array instead. The tools in
        ``src/tools/site_manager.py`` handle both shapes, so the reply is
        passed through as is and typed as such, rather than rejected.
        """
        return await self.get(endpoint, params=params)

    async def list_sites(
        self, page_size: int | None = None, next_token: str | None = None
    ) -> JSONBody:
        """List all sites from Site Manager API.

        Args:
            page_size: Number of sites per page (spec ``pageSize``)
            next_token: Token from the previous page (spec ``nextToken``)

        Returns:
            Response with sites list and, when more pages exist, ``nextToken``
        """
        params = {"pageSize": page_size, "nextToken": next_token}
        return await self._get_object(
            "sites", params={k: v for k, v in params.items() if v is not None}
        )

    async def get_site_health(self, site_id: str | None = None) -> JSONBody:
        """Get health metrics for a site or all sites.

        Args:
            site_id: Optional site identifier. If None, returns health for all sites.

        Returns:
            Health metrics
        """
        endpoint = "sites/health"
        if site_id:
            endpoint = f"sites/{site_id}/health"

        return await self._get_object(endpoint)

    async def get_internet_health(self, site_id: str | None = None) -> JSONBody:
        """Get internet health metrics.

        Args:
            site_id: Optional site identifier. If None, returns aggregate internet health.

        Returns:
            Internet health metrics
        """
        endpoint = "internet/health"
        if site_id:
            endpoint = f"sites/{site_id}/internet/health"

        return await self._get_object(endpoint)

    async def list_vantage_points(self) -> JSONBody:
        """List all Vantage Points.

        Returns:
            Response with Vantage Points list
        """
        return await self._get_object("vantage-points")

    # ISP Metrics endpoints (added 2026-02-16)
    async def get_isp_metrics(
        self,
        metric_type: str,
        begin_timestamp: str | None = None,
        end_timestamp: str | None = None,
        duration: str | None = None,
    ) -> JSONBody:
        """Get ISP metrics for every site on the account (GET isp-metrics/{type}).

        Args:
            metric_type: Interval, ``5m`` or ``1h``
            begin_timestamp: Earliest time (RFC3339)
            end_timestamp: Latest time (RFC3339)
            duration: ``24h`` for 5m, ``7d`` or ``30d`` for 1h. Not with timestamps.

        Returns:
            ISP metrics data
        """
        params = {
            "beginTimestamp": begin_timestamp,
            "endTimestamp": end_timestamp,
            "duration": duration,
        }
        return await self._get_object(
            f"isp-metrics/{metric_type}",
            params={k: v for k, v in params.items() if v is not None},
        )

    async def query_isp_metrics(self, metric_type: str, sites: list[dict[str, Any]]) -> JSONBody:
        """Query ISP metrics for given sites (POST isp-metrics/{type}/query).

        The POST reads only; it changes nothing on the account.

        Args:
            metric_type: Interval, ``5m`` or ``1h``
            sites: ``[{"hostId", "siteId", "beginTimestamp"?, "endTimestamp"?}]``

        Returns:
            ISP metrics query results
        """
        return await self.post(f"isp-metrics/{metric_type}/query", json_data={"sites": sites})

    # SD-WAN endpoints (added 2026-02-16)
    async def list_sdwan_configs(self) -> JSONBody:
        """List all SD-WAN configurations.

        Returns:
            Response with SD-WAN configurations list
        """
        return await self._get_object("sd-wan-configs")

    async def get_sdwan_config(self, config_id: str) -> JSONBody:
        """Get SD-WAN configuration by ID.

        Args:
            config_id: Configuration identifier

        Returns:
            SD-WAN configuration data
        """
        return await self._get_object(f"sd-wan-configs/{config_id}")

    async def get_sdwan_config_status(self, config_id: str) -> JSONBody:
        """Get SD-WAN configuration deployment status.

        Args:
            config_id: Configuration identifier

        Returns:
            SD-WAN configuration status data
        """
        return await self._get_object(f"sd-wan-configs/{config_id}/status")

    # Host Management endpoints (added 2026-02-16)
    async def list_hosts(
        self, page_size: int | None = None, next_token: str | None = None
    ) -> JSONBody:
        """List all managed hosts/consoles.

        Args:
            page_size: Number of hosts per page (spec ``pageSize``)
            next_token: Token from the previous page (spec ``nextToken``)

        Returns:
            Response with hosts list and, when more pages exist, ``nextToken``
        """
        params = {"pageSize": page_size, "nextToken": next_token}
        return await self._get_object(
            "hosts", params={k: v for k, v in params.items() if v is not None}
        )

    async def list_devices(
        self,
        host_ids: list[str] | None = None,
        time: str | None = None,
        page_size: int | None = None,
        next_token: str | None = None,
    ) -> JSONBody:
        """List devices grouped by host (spec ``GET /v1/devices``).

        Args:
            host_ids: Only these hosts (spec ``hostIds[]``, repeated)
            time: Last processed timestamp, RFC 3339 (spec ``time``)
            page_size: Items per page (spec ``pageSize``)
            next_token: Token from the previous page (spec ``nextToken``)

        Returns:
            Response with one entry per host and, when more pages exist, ``nextToken``
        """
        params: dict[str, Any] = {
            "hostIds[]": list(host_ids) if host_ids else None,
            "time": time,
            "pageSize": page_size,
            "nextToken": next_token,
        }
        return await self._get_object(
            "devices", params={k: v for k, v in params.items() if v is not None}
        )

    async def get_host(self, host_id: str) -> JSONBody:
        """Get host details by ID.

        Args:
            host_id: Host identifier

        Returns:
            Host details
        """
        return await self._get_object(f"hosts/{host_id}")

    # Version Control endpoint (added 2026-02-16)
    async def get_version_control(self) -> JSONBody:
        """Get API version control information.

        Returns:
            Version control data
        """
        return await self._get_object("version")
