"""Camera media reads are kept from the viewer role.

These tools make no controller write, so they stay ``@read_tool`` and stay
registered in read-only mode. They return camera images, stream URLs with
access tokens, or a raw Protect GET that can fetch either, so the access
check needs the ``write`` tier.
"""

from pathlib import Path
from typing import Any

import pytest
from fastmcp.server.auth import AccessToken

from src.access import PermissionDeniedError, Principal
from src.config.config import APIType, Settings
from src.fleet import ControllerProfile
from src.fleet.router import FleetRouter
from src.tool_registry import (
    SENSITIVE_READ_TOOLS,
    _make_tool_wrapper,
    is_mutating_tool,
    register_module_tools,
    tool_tier,
)
from src.tools import connector, protect_cameras
from src.utils import tool_kind

from .test_router import StaticRegistry

MEDIA_TOOLS = {
    "get_protect_camera_snapshot": protect_cameras,
    "get_protect_camera_rtsps_streams": protect_cameras,
    "connector_protect_get": connector,
}


@pytest.fixture(autouse=True)
def _fresh_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.utils.audit._audit_logger", None)
    monkeypatch.delenv("UNIFI_AUDIT_CHAIN_KEY", raising=False)
    monkeypatch.delenv("UNIFI_AUDIT_LOG_KEY", raising=False)


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    monkeypatch.setenv("UNIFI_API_KEY", "test-key")  # pragma: allowlist secret
    monkeypatch.setenv("UNIFI_API_TYPE", "local")
    monkeypatch.setenv("UNIFI_LOCAL_HOST", "192.0.2.10")
    monkeypatch.setenv("UNIFI_AUDIT_LOG_PATH", str(tmp_path / "audit.log"))
    return Settings()


@pytest.fixture
def router(settings: Settings) -> FleetRouter:
    profile = ControllerProfile(
        name="hq",
        api_type=APIType.LOCAL,
        api_key="hq-key",  # pragma: allowlist secret
        local_host="192.0.2.10",
    )
    return FleetRouter(settings, StaticRegistry(profile, default="hq"))


def _as(monkeypatch: pytest.MonkeyPatch, role: str) -> None:
    token = AccessToken(
        token="umcp_test",  # noqa: S106
        client_id="t",
        scopes=[],
        claims={"token_id": "tok-1", "name": "t", "role": role},
    )
    monkeypatch.setattr("src.access.get_access_token", lambda: token)


def _stub(name: str) -> Any:
    """A read tool with the same name as a media tool, which makes no request."""

    async def stub(item_id: str, settings: Any = None) -> str:
        return "ok"

    stub.__name__ = name
    stub.__qualname__ = name
    return tool_kind.read_tool(stub)


def test_media_tools_are_listed():
    assert SENSITIVE_READ_TOOLS == frozenset(MEDIA_TOOLS)


@pytest.mark.parametrize("name", sorted(MEDIA_TOOLS))
def test_media_tools_are_reads_with_write_tier(name: str):
    fn = getattr(MEDIA_TOOLS[name], name)

    assert not is_mutating_tool(fn)
    assert tool_tier(fn) == "write"
    assert not Principal(id="t", name="t", role="viewer").can_use(tool_tier(fn))
    assert Principal(id="t", name="t", role="operator").can_use(tool_tier(fn))


@pytest.mark.parametrize("name", sorted(MEDIA_TOOLS))
async def test_viewer_token_is_denied(name, settings, router, monkeypatch):
    _as(monkeypatch, "viewer")
    tool = _make_tool_wrapper(getattr(MEDIA_TOOLS[name], name), settings, router)

    with pytest.raises(PermissionDeniedError, match="needs the 'write' tier"):
        await tool("camera-1", controller="hq")


@pytest.mark.parametrize("role", ["operator", "admin"])
@pytest.mark.parametrize("name", sorted(MEDIA_TOOLS))
async def test_operator_and_admin_tokens_are_allowed(name, role, settings, router, monkeypatch):
    _as(monkeypatch, role)
    tool = _make_tool_wrapper(_stub(name), settings, router)

    assert await tool("camera-1", controller="hq") == "ok"


def test_read_only_mode_registers_media_tools():
    registered: list[str] = []

    class _FakeMCP:
        def tool(self):
            return lambda fn: fn

    settings = type("S", (), {"read_only": True, "dry_run": False})()
    for module in {protect_cameras, connector}:
        registered += register_module_tools(_FakeMCP(), module, settings)

    assert set(MEDIA_TOOLS) <= set(registered)
    assert "update_protect_camera" not in registered
