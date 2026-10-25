"""Tests for Site Manager tools."""

from unittest.mock import AsyncMock, patch

import pytest

from src.tools.site_manager import (
    compare_site_performance,
    get_cross_site_statistics,
    get_internet_health,
    get_site_health_summary,
    get_site_inventory,
    list_all_sites_aggregated,
    list_vantage_points,
    search_across_sites,
)


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""

    # Use a simple object with real attributes instead of MagicMock
    # to avoid MagicMock comparison issues with httpx timeout handling
    class MockSettings:
        log_level = "INFO"
        site_manager_enabled = True
        api_key = "test-key"
        request_timeout = 30.0

        def get_headers(self):
            return {"X-API-Key": "test-key"}

    return MockSettings()


@pytest.fixture
def mock_settings_disabled():
    """Create mock settings with site manager disabled."""

    # Use a simple object with real attributes instead of MagicMock
    class MockSettings:
        log_level = "INFO"
        site_manager_enabled = False
        api_key = "test-key"
        request_timeout = 30.0

        def get_headers(self):
            return {"X-API-Key": "test-key"}

    return MockSettings()


# =============================================================================
# Task 4.1: Test list_all_sites_aggregated
# =============================================================================


@pytest.mark.asyncio
async def test_list_all_sites_aggregated_success(mock_settings):
    """Test successful retrieval of aggregated sites list."""
    mock_response = {
        "data": [
            {
                "site_id": "site-1",
                "name": "Main Office",
                "devices": 5,
                "clients": 25,
            },
            {
                "site_id": "site-2",
                "name": "Branch Office",
                "devices": 3,
                "clients": 10,
            },
        ]
    }

    with patch("src.tools.site_manager.SiteManagerClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.list_sites = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await list_all_sites_aggregated(mock_settings)

        assert len(result) == 2
        assert result[0]["site_id"] == "site-1"
        assert result[0]["name"] == "Main Office"
        assert result[1]["site_id"] == "site-2"
        mock_client.list_sites.assert_called_once()


@pytest.mark.asyncio
async def test_list_all_sites_aggregated_empty(mock_settings):
    """Test retrieval when no sites exist."""
    mock_response = {"data": []}

    with patch("src.tools.site_manager.SiteManagerClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.list_sites = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await list_all_sites_aggregated(mock_settings)

        assert result == []
        mock_client.list_sites.assert_called_once()


@pytest.mark.asyncio
async def test_list_all_sites_aggregated_disabled(mock_settings_disabled):
    """Test that function raises when site manager is disabled."""
    with pytest.raises(ValueError) as excinfo:
        await list_all_sites_aggregated(mock_settings_disabled)

    assert "Site Manager API is not enabled" in str(excinfo.value)


@pytest.mark.asyncio
async def test_list_all_sites_aggregated_alternate_response_format(mock_settings):
    """Test handling of 'sites' key instead of 'data'."""
    mock_response = {
        "sites": [
            {
                "site_id": "site-1",
                "name": "Office",
            }
        ]
    }

    with patch("src.tools.site_manager.SiteManagerClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.list_sites = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await list_all_sites_aggregated(mock_settings)

        assert len(result) == 1
        assert result[0]["site_id"] == "site-1"


# =============================================================================
# Task 4.2: Test get_internet_health
# =============================================================================


@pytest.mark.asyncio
async def test_get_internet_health_all_sites(mock_settings):
    """Test internet health retrieval for all sites (no site_id)."""
    mock_response = {
        "data": {
            "latency_ms": 25.5,
            "packet_loss_percent": 0.1,
            "jitter_ms": 2.3,
            "bandwidth_up_mbps": 100.0,
            "bandwidth_down_mbps": 500.0,
            "status": "healthy",
            "last_tested": "2026-01-05T00:00:00Z",
        }
    }

    with patch("src.tools.site_manager.SiteManagerClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get_internet_health = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await get_internet_health(mock_settings)

        assert result["status"] == "healthy"
        assert result["latency_ms"] == 25.5
        assert result["bandwidth_down_mbps"] == 500.0
        mock_client.get_internet_health.assert_called_once_with(None)


@pytest.mark.asyncio
async def test_get_internet_health_specific_site(mock_settings):
    """Test internet health retrieval for a specific site."""
    mock_response = {
        "data": {
            "site_id": "site-1",
            "latency_ms": 15.0,
            "packet_loss_percent": 0.0,
            "jitter_ms": 1.0,
            "bandwidth_up_mbps": 50.0,
            "bandwidth_down_mbps": 200.0,
            "status": "healthy",
            "last_tested": "2026-01-05T00:00:00Z",
        }
    }

    with patch("src.tools.site_manager.SiteManagerClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get_internet_health = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await get_internet_health(mock_settings, site_id="site-1")

        assert result["site_id"] == "site-1"
        assert result["status"] == "healthy"
        mock_client.get_internet_health.assert_called_once_with("site-1")


@pytest.mark.asyncio
async def test_get_internet_health_degraded(mock_settings):
    """Test internet health when connection is degraded."""
    mock_response = {
        "data": {
            "latency_ms": 150.0,
            "packet_loss_percent": 5.5,
            "jitter_ms": 25.0,
            "bandwidth_up_mbps": 10.0,
            "bandwidth_down_mbps": 50.0,
            "status": "degraded",
            "last_tested": "2026-01-05T00:00:00Z",
        }
    }

    with patch("src.tools.site_manager.SiteManagerClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get_internet_health = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await get_internet_health(mock_settings)

        assert result["status"] == "degraded"
        assert result["packet_loss_percent"] == 5.5


@pytest.mark.asyncio
async def test_get_internet_health_disabled(mock_settings_disabled):
    """Test that function raises when site manager is disabled."""
    with pytest.raises(ValueError) as excinfo:
        await get_internet_health(mock_settings_disabled)

    assert "Site Manager API is not enabled" in str(excinfo.value)


# =============================================================================
# Task 4.3: Test get_site_health_summary and get_cross_site_statistics
# =============================================================================


@pytest.mark.asyncio
async def test_get_site_health_summary_specific_site(mock_settings):
    """Test health summary for a specific site."""
    mock_response = {
        "site_id": "site-1",
        "site_name": "Main Office",
        "status": "healthy",
        "devices_online": 5,
        "devices_total": 5,
        "clients_active": 25,
        "uptime_percentage": 99.9,
        "last_updated": "2026-01-05T00:00:00Z",
    }

    with patch("src.tools.site_manager.SiteManagerClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get_site_health = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await get_site_health_summary(mock_settings, site_id="site-1")

        assert result["site_id"] == "site-1"
        assert result["status"] == "healthy"
        assert result["devices_online"] == 5
        mock_client.get_site_health.assert_called_once_with("site-1")


@pytest.mark.asyncio
async def test_get_site_health_summary_all_sites(mock_settings):
    """Test health summary for all sites."""
    mock_response = {
        "sites": [
            {
                "site_id": "site-1",
                "site_name": "Main Office",
                "status": "healthy",
                "devices_online": 5,
                "devices_total": 5,
                "clients_active": 25,
                "uptime_percentage": 99.9,
                "last_updated": "2026-01-05T00:00:00Z",
            },
            {
                "site_id": "site-2",
                "site_name": "Branch Office",
                "status": "degraded",
                "devices_online": 2,
                "devices_total": 3,
                "clients_active": 10,
                "uptime_percentage": 95.0,
                "last_updated": "2026-01-05T00:00:00Z",
            },
        ]
    }

    with patch("src.tools.site_manager.SiteManagerClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get_site_health = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await get_site_health_summary(mock_settings)

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["site_id"] == "site-1"
        assert result[1]["status"] == "degraded"
        mock_client.get_site_health.assert_called_once_with(None)


@pytest.mark.asyncio
async def test_get_site_health_summary_disabled(mock_settings_disabled):
    """Test that function raises when site manager is disabled."""
    with pytest.raises(ValueError) as excinfo:
        await get_site_health_summary(mock_settings_disabled)

    assert "Site Manager API is not enabled" in str(excinfo.value)


@pytest.mark.asyncio
async def test_get_cross_site_statistics_success(mock_settings):
    """Test cross-site statistics aggregation."""
    mock_sites_response = {
        "data": [
            {"site_id": "site-1", "name": "Site 1"},
            {"site_id": "site-2", "name": "Site 2"},
            {"site_id": "site-3", "name": "Site 3"},
        ]
    }
    mock_health_response = {
        "data": [
            {
                "site_id": "site-1",
                "site_name": "Site 1",
                "status": "healthy",
                "devices_online": 5,
                "devices_total": 5,
                "clients_active": 25,
                "uptime_percentage": 99.9,
                "last_updated": "2026-01-05T00:00:00Z",
            },
            {
                "site_id": "site-2",
                "site_name": "Site 2",
                "status": "degraded",
                "devices_online": 2,
                "devices_total": 3,
                "clients_active": 10,
                "uptime_percentage": 95.0,
                "last_updated": "2026-01-05T00:00:00Z",
            },
            {
                "site_id": "site-3",
                "site_name": "Site 3",
                "status": "down",
                "devices_online": 0,
                "devices_total": 2,
                "clients_active": 0,
                "uptime_percentage": 0.0,
                "last_updated": "2026-01-05T00:00:00Z",
            },
        ]
    }

    with patch("src.tools.site_manager.SiteManagerClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.list_sites = AsyncMock(return_value=mock_sites_response)
        mock_client.get_site_health = AsyncMock(return_value=mock_health_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await get_cross_site_statistics(mock_settings)

        assert result["total_sites"] == 3
        assert result["sites_healthy"] == 1
        assert result["sites_degraded"] == 1
        assert result["sites_down"] == 1
        assert result["total_devices"] == 10  # 5 + 3 + 2
        assert result["devices_online"] == 7  # 5 + 2 + 0
        assert result["total_clients"] == 35  # 25 + 10 + 0
        assert len(result["site_summaries"]) == 3


@pytest.mark.asyncio
async def test_get_cross_site_statistics_empty(mock_settings):
    """Test cross-site statistics with no sites."""
    mock_sites_response = {"data": []}
    mock_health_response = {"data": []}

    with patch("src.tools.site_manager.SiteManagerClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.list_sites = AsyncMock(return_value=mock_sites_response)
        mock_client.get_site_health = AsyncMock(return_value=mock_health_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await get_cross_site_statistics(mock_settings)

        assert result["total_sites"] == 0
        assert result["sites_healthy"] == 0
        assert result["total_devices"] == 0
        assert len(result["site_summaries"]) == 0


@pytest.mark.asyncio
async def test_get_cross_site_statistics_disabled(mock_settings_disabled):
    """Test that function raises when site manager is disabled."""
    with pytest.raises(ValueError) as excinfo:
        await get_cross_site_statistics(mock_settings_disabled)

    assert "Site Manager API is not enabled" in str(excinfo.value)


# =============================================================================
# Task 4.4: Test list_vantage_points
# =============================================================================


@pytest.mark.asyncio
async def test_list_vantage_points_success(mock_settings):
    """Test successful retrieval of Vantage Points."""
    mock_response = {
        "vantage_points": [
            {
                "vantage_point_id": "vp-1",
                "name": "New York Office",
                "location": "New York, NY",
                "latitude": 40.7128,
                "longitude": -74.0060,
                "status": "active",
                "site_ids": ["site-1", "site-2"],
            },
            {
                "vantage_point_id": "vp-2",
                "name": "London Office",
                "location": "London, UK",
                "latitude": 51.5074,
                "longitude": -0.1278,
                "status": "active",
                "site_ids": ["site-3"],
            },
        ]
    }

    with patch("src.tools.site_manager.SiteManagerClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.list_vantage_points = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await list_vantage_points(mock_settings)

        assert len(result) == 2
        assert result[0]["vantage_point_id"] == "vp-1"
        assert result[0]["name"] == "New York Office"
        assert result[0]["status"] == "active"
        assert len(result[0]["site_ids"]) == 2
        mock_client.list_vantage_points.assert_called_once()


@pytest.mark.asyncio
async def test_list_vantage_points_empty(mock_settings):
    """Test retrieval when no Vantage Points exist."""
    mock_response = {"vantage_points": []}

    with patch("src.tools.site_manager.SiteManagerClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.list_vantage_points = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await list_vantage_points(mock_settings)

        assert result == []
        mock_client.list_vantage_points.assert_called_once()


@pytest.mark.asyncio
async def test_list_vantage_points_with_inactive(mock_settings):
    """Test Vantage Points including inactive ones."""
    mock_response = {
        "vantage_points": [
            {
                "vantage_point_id": "vp-1",
                "name": "Active Office",
                "location": "NYC",
                "status": "active",
                "site_ids": ["site-1"],
            },
            {
                "vantage_point_id": "vp-2",
                "name": "Inactive Office",
                "location": "LA",
                "status": "inactive",
                "site_ids": [],
            },
        ]
    }

    with patch("src.tools.site_manager.SiteManagerClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.list_vantage_points = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await list_vantage_points(mock_settings)

        assert len(result) == 2
        assert result[0]["status"] == "active"
        assert result[1]["status"] == "inactive"


@pytest.mark.asyncio
async def test_list_vantage_points_disabled(mock_settings_disabled):
    """Test that function raises when site manager is disabled."""
    with pytest.raises(ValueError) as excinfo:
        await list_vantage_points(mock_settings_disabled)

    assert "Site Manager API is not enabled" in str(excinfo.value)


@pytest.mark.asyncio
async def test_list_vantage_points_list_format(mock_settings):
    """Test handling when response is a list instead of dict."""
    mock_response = [
        {
            "vantage_point_id": "vp-1",
            "name": "Office",
            "status": "active",
            "site_ids": [],
        }
    ]

    with patch("src.tools.site_manager.SiteManagerClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.list_vantage_points = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await list_vantage_points(mock_settings)

        assert len(result) == 1
        assert result[0]["vantage_point_id"] == "vp-1"


# =============================================================================
# Task 4.5: Test get_site_inventory
# =============================================================================


@pytest.mark.asyncio
async def test_get_site_inventory_specific_site(mock_settings):
    """Test inventory retrieval for a specific site."""
    mock_response = {
        "data": {
            "site_id": "site-1",
            "name": "Main Office",
            "device_count": 15,
            "device_types": {"uap": 8, "usw": 5, "ugw": 2},
            "client_count": 75,
            "network_count": 5,
            "ssid_count": 3,
            "uplink_count": 2,
            "vpn_tunnel_count": 4,
            "firewall_rule_count": 25,
            "last_updated": "2026-01-24T00:00:00Z",
        }
    }

    with patch("src.tools.site_manager.SiteManagerClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await get_site_inventory(mock_settings, site_id="site-1")

        assert result["site_id"] == "site-1"
        assert result["site_name"] == "Main Office"
        assert result["device_count"] == 15
        assert result["device_types"]["uap"] == 8
        assert result["client_count"] == 75
        assert result["network_count"] == 5
        mock_client.get.assert_called_once_with("sites/site-1")


@pytest.mark.asyncio
async def test_get_site_inventory_all_sites(mock_settings):
    """Test inventory retrieval for all sites."""
    mock_response = {
        "data": [
            {
                "site_id": "site-1",
                "name": "Office 1",
                "device_count": 10,
                "device_types": {"uap": 6, "usw": 4},
                "client_count": 50,
                "network_count": 3,
                "ssid_count": 2,
                "uplink_count": 1,
                "vpn_tunnel_count": 0,
                "firewall_rule_count": 15,
                "last_updated": "2026-01-24T00:00:00Z",
            },
            {
                "site_id": "site-2",
                "name": "Office 2",
                "device_count": 5,
                "device_types": {"uap": 3, "usw": 2},
                "client_count": 25,
                "network_count": 2,
                "ssid_count": 1,
                "uplink_count": 1,
                "vpn_tunnel_count": 2,
                "firewall_rule_count": 10,
                "last_updated": "2026-01-24T00:00:00Z",
            },
        ]
    }

    with patch("src.tools.site_manager.SiteManagerClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.list_sites = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await get_site_inventory(mock_settings)

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["site_id"] == "site-1"
        assert result[0]["device_count"] == 10
        assert result[1]["site_id"] == "site-2"
        assert result[1]["client_count"] == 25
        mock_client.list_sites.assert_called_once()


@pytest.mark.asyncio
async def test_get_site_inventory_disabled(mock_settings_disabled):
    """Test that function raises when site manager is disabled."""
    with pytest.raises(ValueError) as excinfo:
        await get_site_inventory(mock_settings_disabled)

    assert "Site Manager API is not enabled" in str(excinfo.value)


@pytest.mark.asyncio
async def test_get_site_inventory_empty_devices(mock_settings):
    """Test inventory with no devices."""
    mock_response = {
        "data": {
            "site_id": "site-1",
            "name": "New Site",
            "device_count": 0,
            "device_types": {},
            "client_count": 0,
            "network_count": 1,
            "ssid_count": 0,
            "uplink_count": 0,
            "vpn_tunnel_count": 0,
            "firewall_rule_count": 0,
            "last_updated": "2026-01-24T00:00:00Z",
        }
    }

    with patch("src.tools.site_manager.SiteManagerClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await get_site_inventory(mock_settings, site_id="site-1")

        assert result["device_count"] == 0
        assert result["client_count"] == 0


# =============================================================================
# Task 4.6: Test compare_site_performance
# =============================================================================


@pytest.mark.asyncio
async def test_compare_site_performance_success(mock_settings):
    """Test successful performance comparison across sites."""
    mock_health_response = {
        "data": [
            {
                "site_id": "site-1",
                "site_name": "Best Site",
                "status": "healthy",
                "devices_online": 10,
                "devices_total": 10,
                "clients_active": 50,
                "uptime_percentage": 99.9,
                "last_updated": "2026-01-24T00:00:00Z",
            },
            {
                "site_id": "site-2",
                "site_name": "Average Site",
                "status": "healthy",
                "devices_online": 8,
                "devices_total": 10,
                "clients_active": 40,
                "uptime_percentage": 95.0,
                "last_updated": "2026-01-24T00:00:00Z",
            },
            {
                "site_id": "site-3",
                "site_name": "Worst Site",
                "status": "degraded",
                "devices_online": 5,
                "devices_total": 10,
                "clients_active": 20,
                "uptime_percentage": 80.0,
                "last_updated": "2026-01-24T00:00:00Z",
            },
        ]
    }

    mock_internet_response = {
        "data": [
            {
                "site_id": "site-1",
                "latency_ms": 10.0,
                "bandwidth_up_mbps": 100.0,
                "bandwidth_down_mbps": 500.0,
            },
            {
                "site_id": "site-2",
                "latency_ms": 25.0,
                "bandwidth_up_mbps": 50.0,
                "bandwidth_down_mbps": 250.0,
            },
            {
                "site_id": "site-3",
                "latency_ms": 150.0,
                "bandwidth_up_mbps": 20.0,
                "bandwidth_down_mbps": 100.0,
            },
        ]
    }

    with patch("src.tools.site_manager.SiteManagerClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get_site_health = AsyncMock(return_value=mock_health_response)
        mock_client.get_internet_health = AsyncMock(return_value=mock_internet_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await compare_site_performance(mock_settings)

        assert result["total_sites"] == 3
        assert result["best_performing_site"]["site_id"] == "site-1"
        assert result["worst_performing_site"]["site_id"] == "site-3"
        assert result["average_uptime"] == pytest.approx((99.9 + 95.0 + 80.0) / 3)
        assert result["average_latency_ms"] == pytest.approx((10.0 + 25.0 + 150.0) / 3)
        assert len(result["site_metrics"]) == 3


@pytest.mark.asyncio
async def test_compare_site_performance_empty(mock_settings):
    """Test performance comparison with no sites."""
    mock_health_response = {"data": []}
    mock_internet_response = {"data": []}

    with patch("src.tools.site_manager.SiteManagerClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get_site_health = AsyncMock(return_value=mock_health_response)
        mock_client.get_internet_health = AsyncMock(return_value=mock_internet_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await compare_site_performance(mock_settings)

        assert result["total_sites"] == 0
        assert result["best_performing_site"] is None
        assert result["worst_performing_site"] is None
        assert result["average_uptime"] == 0.0


@pytest.mark.asyncio
async def test_compare_site_performance_disabled(mock_settings_disabled):
    """Test that function raises when site manager is disabled."""
    with pytest.raises(ValueError) as excinfo:
        await compare_site_performance(mock_settings_disabled)

    assert "Site Manager API is not enabled" in str(excinfo.value)


@pytest.mark.asyncio
async def test_compare_site_performance_single_site(mock_settings):
    """Test performance comparison with only one site."""
    mock_health_response = {
        "data": [
            {
                "site_id": "site-1",
                "site_name": "Only Site",
                "status": "healthy",
                "devices_online": 10,
                "devices_total": 10,
                "clients_active": 50,
                "uptime_percentage": 99.5,
                "last_updated": "2026-01-24T00:00:00Z",
            }
        ]
    }

    mock_internet_response = {
        "data": [{"site_id": "site-1", "latency_ms": 15.0, "bandwidth_up_mbps": 100.0}]
    }

    with patch("src.tools.site_manager.SiteManagerClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get_site_health = AsyncMock(return_value=mock_health_response)
        mock_client.get_internet_health = AsyncMock(return_value=mock_internet_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await compare_site_performance(mock_settings)

        assert result["total_sites"] == 1
        assert result["best_performing_site"]["site_id"] == "site-1"
        assert result["worst_performing_site"]["site_id"] == "site-1"
        assert result["average_uptime"] == 99.5


# =============================================================================
# Task 4.7: Test search_across_sites
# =============================================================================


@pytest.mark.asyncio
async def test_search_across_sites_device(mock_settings):
    """Test searching for devices across sites."""
    mock_response = {
        "data": [
            {
                "site_id": "site-1",
                "name": "Office 1",
                "devices": [
                    {"name": "AP-Living-Room", "mac": "aa:bb:cc:dd:ee:01", "type": "uap"},
                    {"name": "Switch-Main", "mac": "aa:bb:cc:dd:ee:02", "type": "usw"},
                ],
            },
            {
                "site_id": "site-2",
                "name": "Office 2",
                "devices": [{"name": "AP-Conference", "mac": "aa:bb:cc:dd:ee:03", "type": "uap"}],
            },
        ]
    }

    with patch("src.tools.site_manager.SiteManagerClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.list_sites = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await search_across_sites(mock_settings, query="living", search_type="device")

        assert result["total_results"] == 1
        assert result["search_query"] == "living"
        assert result["result_type"] == "device"
        assert result["results"][0]["type"] == "device"
        assert result["results"][0]["site_id"] == "site-1"
        assert result["results"][0]["resource"]["name"] == "AP-Living-Room"


@pytest.mark.asyncio
async def test_search_across_sites_all(mock_settings):
    """Test searching all resource types."""
    mock_response = {
        "data": [
            {
                "site_id": "site-1",
                "name": "Office 1",
                "devices": [{"name": "Test-Device", "mac": "aa:bb:cc:dd:ee:01", "type": "uap"}],
                "clients": [
                    {"name": "Test-Laptop", "mac": "11:22:33:44:55:01", "ip": "192.168.2.10"}
                ],
                "networks": [{"name": "Test-VLAN", "vlan": 10}],
            }
        ]
    }

    with patch("src.tools.site_manager.SiteManagerClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.list_sites = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await search_across_sites(mock_settings, query="test", search_type="all")

        assert result["total_results"] == 3
        assert result["result_type"] == "all"
        assert len(result["results"]) == 3
        types_found = {r["type"] for r in result["results"]}
        assert types_found == {"device", "client", "network"}


@pytest.mark.asyncio
async def test_search_across_sites_no_results(mock_settings):
    """Test searching with no matching results."""
    mock_response = {
        "data": [
            {
                "site_id": "site-1",
                "name": "Office 1",
                "devices": [{"name": "AP-Main", "mac": "aa:bb:cc:dd:ee:01", "type": "uap"}],
            }
        ]
    }

    with patch("src.tools.site_manager.SiteManagerClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.list_sites = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await search_across_sites(mock_settings, query="nonexistent", search_type="device")

        assert result["total_results"] == 0
        assert len(result["results"]) == 0


@pytest.mark.asyncio
async def test_search_across_sites_invalid_type(mock_settings):
    """Test searching with invalid search type."""
    with pytest.raises(ValueError) as excinfo:
        await search_across_sites(mock_settings, query="test", search_type="invalid")

    assert "search_type must be one of" in str(excinfo.value)


@pytest.mark.asyncio
async def test_search_across_sites_disabled(mock_settings_disabled):
    """Test that function raises when site manager is disabled."""
    with pytest.raises(ValueError) as excinfo:
        await search_across_sites(mock_settings_disabled, query="test")

    assert "Site Manager API is not enabled" in str(excinfo.value)


@pytest.mark.asyncio
async def test_search_across_sites_mac_address(mock_settings):
    """Test searching by MAC address."""
    mock_response = {
        "data": [
            {
                "site_id": "site-1",
                "name": "Office 1",
                "devices": [{"name": "AP-Main", "mac": "aa:bb:cc:dd:ee:01", "type": "uap"}],
            }
        ]
    }

    with patch("src.tools.site_manager.SiteManagerClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.list_sites = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await search_across_sites(
            mock_settings, query="aa:bb:cc:dd:ee:01", search_type="device"
        )

        assert result["total_results"] == 1
        assert result["results"][0]["resource"]["mac"] == "aa:bb:cc:dd:ee:01"


# =============================================================================
# Tests for ISP Metrics Tools (spec: GET /v1/isp-metrics/{type},
# POST /v1/isp-metrics/{type}/query)
# =============================================================================


def _client_cm(**methods):
    mock_client = AsyncMock()
    for name, value in methods.items():
        setattr(mock_client, name, AsyncMock(return_value=value))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock()
    return mock_client


_ISP_ENTRY_S1 = {
    "metricType": "5m",
    "hostId": "host-1",
    "siteId": "site-1",
    "periods": [
        {
            "metricTime": "2026-02-16T12:00:00Z",
            "version": "1",
            "data": {"wan": {"avgLatency": 15, "download_kbps": 500000, "ispName": "ISP 1"}},
        }
    ],
}
_ISP_ENTRY_S2 = {**_ISP_ENTRY_S1, "siteId": "site-2"}


@pytest.mark.asyncio
async def test_get_isp_metrics_spec_shape(mock_settings):
    """The spec reply is data[] of {metricType, hostId, siteId, periods}."""
    from src.tools.site_manager import get_isp_metrics

    mock_client = _client_cm(get_isp_metrics={"data": [_ISP_ENTRY_S1, _ISP_ENTRY_S2]})
    with patch("src.tools.site_manager.SiteManagerClient", return_value=mock_client):
        result = await get_isp_metrics(mock_settings, interval="1h", duration="7d")

    assert result["count"] == 2
    assert result["interval"] == "1h"
    assert result["data"][0]["periods"][0]["data"]["wan"]["avgLatency"] == 15
    mock_client.get_isp_metrics.assert_called_once_with(
        "1h", begin_timestamp=None, end_timestamp=None, duration="7d"
    )


@pytest.mark.asyncio
async def test_get_isp_metrics_filters_site(mock_settings):
    """site_id filters the account-wide reply on data[].siteId."""
    from src.tools.site_manager import get_isp_metrics

    mock_client = _client_cm(get_isp_metrics={"data": [_ISP_ENTRY_S1, _ISP_ENTRY_S2]})
    with patch("src.tools.site_manager.SiteManagerClient", return_value=mock_client):
        result = await get_isp_metrics(mock_settings, "site-2")

    assert result["count"] == 1
    assert result["data"][0]["siteId"] == "site-2"
    mock_client.get_isp_metrics.assert_called_once_with(
        "5m", begin_timestamp=None, end_timestamp=None, duration=None
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs",
    [
        {"interval": "15m"},
        {"interval": "5m", "duration": "7d"},
        {"interval": "1h", "duration": "24h"},
        {"duration": "24h", "begin_timestamp": "2026-01-01T00:00:00Z"},
    ],
)
async def test_get_isp_metrics_rejects_bad_args(mock_settings, kwargs):
    from src.tools.site_manager import get_isp_metrics
    from src.utils.exceptions import ValidationError

    mock_client = _client_cm(get_isp_metrics={"data": []})
    with patch("src.tools.site_manager.SiteManagerClient", return_value=mock_client):
        with pytest.raises(ValidationError):
            await get_isp_metrics(mock_settings, **kwargs)
    mock_client.get_isp_metrics.assert_not_called()


@pytest.mark.asyncio
async def test_query_isp_metrics_posts_host_and_site(mock_settings):
    """The query body is {"sites": [{hostId, siteId, beginTimestamp, endTimestamp}]}."""
    from src.tools.site_manager import query_isp_metrics

    mock_response = {
        "data": {"metrics": [_ISP_ENTRY_S1], "status": "partialSuccess", "message": "m"}
    }
    mock_client = _client_cm(query_isp_metrics=mock_response)
    with patch("src.tools.site_manager.SiteManagerClient", return_value=mock_client):
        result = await query_isp_metrics(
            mock_settings,
            site_id="site-1",
            host_id="host-1",
            interval="1h",
            start_time="2026-02-16T00:00:00Z",
        )

    assert result["count"] == 1
    assert result["status"] == "partialSuccess"
    assert result["data"][0]["siteId"] == "site-1"
    mock_client.query_isp_metrics.assert_called_once_with(
        "1h",
        [{"hostId": "host-1", "siteId": "site-1", "beginTimestamp": "2026-02-16T00:00:00Z"}],
    )


@pytest.mark.asyncio
async def test_query_isp_metrics_rejects_bad_interval(mock_settings):
    from src.tools.site_manager import query_isp_metrics
    from src.utils.exceptions import ValidationError

    mock_client = _client_cm(query_isp_metrics={})
    with patch("src.tools.site_manager.SiteManagerClient", return_value=mock_client):
        with pytest.raises(ValidationError):
            await query_isp_metrics(mock_settings, site_id="s", host_id="h", interval="1d")


# =============================================================================
# Tests for SD-WAN Configuration Tools (spec: /v1/sd-wan-configs)
# =============================================================================


@pytest.mark.asyncio
async def test_list_sdwan_configs_spec_shape(mock_settings):
    """The spec list item is {id, name, type}."""
    from src.tools.site_manager import list_sdwan_configs

    mock_response = {"data": [{"id": "config-1", "name": "HBSP", "type": "sdwan-hbsp"}]}
    mock_client = _client_cm(list_sdwan_configs=mock_response)
    with patch("src.tools.site_manager.SiteManagerClient", return_value=mock_client):
        result = await list_sdwan_configs(mock_settings)

    assert result == [{"id": "config-1", "name": "HBSP", "type": "sdwan-hbsp"}]


@pytest.mark.asyncio
async def test_get_sdwan_config_spec_shape(mock_settings):
    """The spec detail carries variant, settings, hubs and spokes."""
    from src.tools.site_manager import get_sdwan_config

    config = {
        "id": "config-1",
        "name": "HBSP",
        "type": "sdwan-hbsp",
        "variant": "failover",
        "settings": {"hubsInterconnect": True},
        "hubs": [{"id": "hub-1", "hostId": "h1", "siteId": "s1"}],
        "spokes": [{"id": "spoke-1", "hostId": "h2", "siteId": "s2"}],
    }
    mock_client = _client_cm(get_sdwan_config={"data": config})
    with patch("src.tools.site_manager.SiteManagerClient", return_value=mock_client):
        result = await get_sdwan_config(mock_settings, "config-1")

    assert result == config
    mock_client.get_sdwan_config.assert_called_once_with("config-1")


@pytest.mark.asyncio
async def test_get_sdwan_config_status_spec_shape(mock_settings):
    """The spec status is {id, fingerprint, updatedAt, hubs[]}."""
    from src.tools.site_manager import get_sdwan_config_status

    status = {"id": "config-1", "fingerprint": "f1", "updatedAt": 1700000000, "hubs": []}
    mock_client = _client_cm(get_sdwan_config_status={"data": status})
    with patch("src.tools.site_manager.SiteManagerClient", return_value=mock_client):
        result = await get_sdwan_config_status(mock_settings, "config-1")

    assert result == status
    mock_client.get_sdwan_config_status.assert_called_once_with("config-1")


# =============================================================================
# Tests for Host Management Tools (spec pagination: pageSize, nextToken)
# =============================================================================


@pytest.mark.asyncio
async def test_list_hosts_returns_next_token(mock_settings):
    from src.tools.site_manager import list_hosts

    mock_response = {"data": [{"id": "host-1", "type": "console"}], "nextToken": "t2"}
    mock_client = _client_cm(list_hosts=mock_response)
    with patch("src.tools.site_manager.SiteManagerClient", return_value=mock_client):
        result = await list_hosts(mock_settings, page_size=1, next_token="t1")

    assert result == {"count": 1, "data": [{"id": "host-1", "type": "console"}], "next_token": "t2"}
    mock_client.list_hosts.assert_called_once_with(page_size=1, next_token="t1")


@pytest.mark.asyncio
async def test_list_hosts_bare_array_reply(mock_settings):
    from src.tools.site_manager import list_hosts

    mock_client = _client_cm(list_hosts=[{"id": "host-1"}])
    with patch("src.tools.site_manager.SiteManagerClient", return_value=mock_client):
        result = await list_hosts(mock_settings)

    assert result == {"count": 1, "data": [{"id": "host-1"}], "next_token": None}


@pytest.mark.asyncio
async def test_list_site_manager_devices(mock_settings):
    from src.tools.site_manager import list_site_manager_devices

    host = {
        "hostId": "host-1",
        "hostName": "UDM",
        "devices": [{"id": "d1", "mac": "aa:bb:cc:dd:ee:ff", "status": "online"}],
        "updatedAt": "2026-10-25T10:00:00Z",
    }
    mock_client = _client_cm(list_devices={"data": [host], "nextToken": "t2"})
    with patch("src.tools.site_manager.SiteManagerClient", return_value=mock_client):
        result = await list_site_manager_devices(
            mock_settings, host_ids=["host-1"], page_size=50, next_token="t1"
        )

    mock_client.list_devices.assert_called_once_with(
        host_ids=["host-1"], time=None, page_size=50, next_token="t1"
    )
    assert result == {"count": 1, "device_count": 1, "data": [host], "next_token": "t2"}


@pytest.mark.asyncio
async def test_get_host_success(mock_settings):
    """Test successful retrieval of host details."""
    from src.tools.site_manager import get_host

    mock_response = {
        "data": {
            "host_id": "host-1",
            "hostname": "controller-01",
            "ip_address": "192.168.1.1",
            "mac_address": "00:11:22:33:44:55",
            "model": "UDM-Pro",
            "version": "10.0.156",
            "site_count": 2,
            "status": "online",
            "last_seen": "2026-02-16T12:00:00Z",
        }
    }

    with patch("src.tools.site_manager.SiteManagerClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get_host = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await get_host(mock_settings, "host-1")

        assert result["host_id"] == "host-1"
        assert result["hostname"] == "controller-01"
        mock_client.get_host.assert_called_once_with("host-1")


# =============================================================================
# Tests for Version Control Tool (added 2026-02-16)
# =============================================================================


@pytest.mark.asyncio
async def test_get_version_control_success(mock_settings):
    """Test successful retrieval of version control info."""
    from src.tools.site_manager import get_version_control

    mock_response = {
        "data": {
            "current_version": "v1.0.0",
            "latest_version": "v1.1.0",
            "deprecated_versions": ["v0.9.0", "v0.8.0"],
            "changelog_url": "https://developer.ui.com/changelog",
            "upgrade_recommended": True,
            "min_supported_version": "v0.9.0",
        }
    }

    with patch("src.tools.site_manager.SiteManagerClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get_version_control = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await get_version_control(mock_settings)

        assert result["current_version"] == "v1.0.0"
        assert result["latest_version"] == "v1.1.0"
        assert result["upgrade_recommended"] is True
        mock_client.get_version_control.assert_called_once()
