"""Unit tests for UniFi Protect camera tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tools.protect_cameras import get_protect_camera, list_protect_cameras
from src.utils.exceptions import ValidationError


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.log_level = "INFO"
    settings.get_protect_integration_path = MagicMock(
        side_effect=lambda endpoint: f"/integration/v1/{endpoint.lstrip('/')}"
    )
    return settings


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.authenticate = AsyncMock()
    client.get = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


@pytest.mark.asyncio
async def test_list_protect_cameras_success(mock_settings, mock_client):
    mock_response = {
        "offset": 0,
        "limit": 10,
        "count": 2,
        "totalCount": 2,
        "data": [
            {"id": "cam-1", "name": "Front Door", "model": "G4 Pro", "isRecording": True},
            {"id": "cam-2", "name": "Garage", "model": "G5 Bullet", "isRecording": False},
        ],
    }
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("src.tools.protect_cameras.ProtectClient", return_value=mock_client):
        result = await list_protect_cameras(mock_settings, limit=10, offset=0)

    mock_client.authenticate.assert_awaited_once()
    mock_client.get.assert_awaited_once_with("/integration/v1/cameras")
    assert result["count"] == 2
    assert result["data"][0]["id"] == "cam-1"
    assert result["data"][0]["name"] == "Front Door"


@pytest.mark.asyncio
async def test_get_protect_camera_success(mock_settings, mock_client):
    mock_response = {"id": "cam-1", "name": "Front Door", "model": "G4 Pro", "isRecording": True}
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("src.tools.protect_cameras.ProtectClient", return_value=mock_client):
        result = await get_protect_camera("cam-1", mock_settings)

    mock_client.authenticate.assert_awaited_once()
    mock_client.get.assert_awaited_once_with("/integration/v1/cameras/cam-1")
    assert result["id"] == "cam-1"
    assert result["model"] == "G4 Pro"


@pytest.mark.asyncio
async def test_get_protect_camera_empty_id_raises(mock_settings):
    with pytest.raises(ValidationError, match="camera_id"):
        await get_protect_camera("", mock_settings)


@pytest.mark.asyncio
async def test_list_protect_cameras_top_level_array(mock_settings, mock_client):
    mock_client.get = AsyncMock(
        return_value=[{"id": "cam-1", "name": "Front Door", "model": "G4 Pro", "isRecording": True}]
    )

    with patch("src.tools.protect_cameras.ProtectClient", return_value=mock_client):
        result = await list_protect_cameras(mock_settings)

    assert result["count"] == 1
    assert result["totalCount"] == 1
    assert len(result["data"]) == 1


@pytest.mark.asyncio
async def test_list_protect_cameras_unexpected_response_raises(mock_settings, mock_client):
    mock_client.get = AsyncMock(return_value=None)

    with patch("src.tools.protect_cameras.ProtectClient", return_value=mock_client):
        with pytest.raises(ValueError, match="Unexpected Protect inventory response type"):
            await list_protect_cameras(mock_settings)


# Spec 7.3.70 camera shape: no model, firmware, recording or PTZ field.
_SPEC_CAMERA = {
    "id": "cam-1",
    "modelKey": "camera",
    "state": "CONNECTED",
    "name": "Front Door",
    "type": "UVC G4 Doorbell Pro",
    "guid": "g-1",
    "mac": "AABBCCDDEEFF",
    "isMicEnabled": True,
    "micVolume": 80,
    "osdSettings": {"isNameEnabled": True},
    "ledSettings": {"isEnabled": True},
    "lcdMessage": {},
    "activePatrolSlot": None,
    "videoMode": "default",
    "hdrType": "auto",
    "hasPackageCamera": True,
    "smartDetectSettings": {"objectTypes": ["person"], "audioTypes": []},
    "featureFlags": {
        "hasMic": True,
        "hasSpeaker": True,
        "hasHdr": True,
        "hasLedStatus": True,
        "supportFullHdSnapshot": True,
        "smartDetectTypes": ["person", "vehicle"],
        "smartDetectAudioTypes": [],
        "videoModes": ["default"],
    },
}


def test_camera_model_maps_spec_fields():
    from src.models import ProtectCamera

    camera = ProtectCamera.model_validate(_SPEC_CAMERA).model_dump(by_alias=True)

    assert camera["model"] == "UVC G4 Doorbell Pro"
    assert camera["hasMic"] is True
    assert camera["hasSpeaker"] is True
    assert camera["modelKey"] == "camera"
    assert camera["isMicEnabled"] is True
    assert camera["micVolume"] == 80
    assert camera["videoMode"] == "default"
    assert camera["hdrType"] == "auto"
    assert camera["hasPackageCamera"] is True
    assert camera["featureFlags"]["smartDetectTypes"] == ["person", "vehicle"]
    assert camera["smartDetectSettings"]["objectTypes"] == ["person"]
    assert camera["osdSettings"] == {"isNameEnabled": True}


def test_camera_model_keeps_explicit_legacy_fields():
    from src.models import ProtectCamera

    camera = ProtectCamera.model_validate(
        {"id": "c", "name": "n", "model": "G4 Pro", "hasMic": False, "type": "x"}
    ).model_dump(by_alias=True)

    assert camera["model"] == "G4 Pro"
    assert camera["hasMic"] is False


@pytest.mark.asyncio
async def test_list_protect_cameras_spec_array_paginates_locally(mock_settings, mock_client):
    """The spec lists no query params for /cameras, so page the array here."""
    cams = [dict(_SPEC_CAMERA, id=f"cam-{i}") for i in range(3)]
    mock_client.get = AsyncMock(return_value=cams)

    with patch("src.tools.protect_cameras.ProtectClient", return_value=mock_client):
        result = await list_protect_cameras(mock_settings, limit=1, offset=1)

    mock_client.get.assert_awaited_once_with("/integration/v1/cameras")
    assert result["totalCount"] == 3
    assert result["count"] == 1
    assert [c["id"] for c in result["data"]] == ["cam-1"]
    assert result["data"][0]["model"] == "UVC G4 Doorbell Pro"


# P1: PATCH /v1/cameras/{id}
# P2: POST/GET/DELETE /v1/cameras/{id}/rtsps-stream


@pytest.fixture
def write_client():
    client = AsyncMock()
    client.authenticate = AsyncMock()
    client.patch = AsyncMock(return_value=dict(_SPEC_CAMERA, name="Porch"))
    client.post = AsyncMock(return_value={"high": "rtsps://h", "low": "rtsps://l"})
    client.get = AsyncMock(
        return_value={"high": "rtsps://h", "medium": None, "low": None, "package": None}
    )
    client.delete = AsyncMock(return_value=None)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


@pytest.mark.asyncio
async def test_update_protect_camera_patches_spec_body(mock_settings, write_client):
    from src.tools.protect_cameras import update_protect_camera

    with patch("src.tools.protect_cameras.ProtectClient", return_value=write_client):
        result = await update_protect_camera(
            "cam-1",
            mock_settings,
            name="Porch",
            osd_settings={"isNameEnabled": False},
            led_settings={"isEnabled": False},
            lcd_message={"type": "DO_NOT_DISTURB"},
            mic_volume=50,
            video_mode="highFps",
            hdr_type="off",
            smart_detect_settings={"objectTypes": ["person"]},
            confirm=True,
        )

    write_client.patch.assert_awaited_once_with(
        "/integration/v1/cameras/cam-1",
        json_data={
            "name": "Porch",
            "osdSettings": {"isNameEnabled": False},
            "ledSettings": {"isEnabled": False},
            "lcdMessage": {"type": "DO_NOT_DISTURB"},
            "micVolume": 50,
            "videoMode": "highFps",
            "hdrType": "off",
            "smartDetectSettings": {"objectTypes": ["person"]},
        },
    )
    assert result["name"] == "Porch"
    assert result["model"] == "UVC G4 Doorbell Pro"


@pytest.mark.asyncio
@pytest.mark.parametrize("confirm", [False, "false"])
async def test_update_protect_camera_requires_confirm(mock_settings, confirm):
    from src.tools.protect_cameras import update_protect_camera

    with patch("src.tools.protect_cameras.ProtectClient") as client_cls:
        with pytest.raises(ValidationError):
            await update_protect_camera("cam-1", mock_settings, name="x", confirm=confirm)
    client_cls.assert_not_called()


@pytest.mark.asyncio
async def test_update_protect_camera_dry_run(mock_settings):
    from src.tools.protect_cameras import update_protect_camera

    with patch("src.tools.protect_cameras.ProtectClient") as client_cls:
        result = await update_protect_camera("cam-1", mock_settings, mic_volume=10, dry_run=True)
    client_cls.assert_not_called()
    assert result == {
        "dry_run": True,
        "operation": "update_protect_camera",
        "camera_id": "cam-1",
        "payload": {"micVolume": 10},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"mic_volume": 101},
        {"mic_volume": -1},
        {"video_mode": "turbo"},
        {"hdr_type": "maybe"},
    ],
)
async def test_update_protect_camera_rejects_bad_args(mock_settings, kwargs):
    from src.tools.protect_cameras import update_protect_camera

    with patch("src.tools.protect_cameras.ProtectClient") as client_cls:
        with pytest.raises(ValidationError):
            await update_protect_camera("cam-1", mock_settings, confirm=True, **kwargs)
    client_cls.assert_not_called()


@pytest.mark.asyncio
async def test_create_protect_camera_rtsps_stream(mock_settings, write_client):
    from src.tools.protect_cameras import create_protect_camera_rtsps_stream

    with patch("src.tools.protect_cameras.ProtectClient", return_value=write_client):
        result = await create_protect_camera_rtsps_stream(
            "cam-1", mock_settings, qualities=["high", "low"], confirm=True
        )

    write_client.post.assert_awaited_once_with(
        "/integration/v1/cameras/cam-1/rtsps-stream",
        json_data={"qualities": ["high", "low"]},
    )
    assert result == {
        "success": True,
        "camera_id": "cam-1",
        "streams": {"high": "rtsps://h", "low": "rtsps://l"},
    }


@pytest.mark.asyncio
async def test_create_protect_camera_rtsps_stream_dry_run(mock_settings):
    from src.tools.protect_cameras import create_protect_camera_rtsps_stream

    with patch("src.tools.protect_cameras.ProtectClient") as client_cls:
        result = await create_protect_camera_rtsps_stream(
            "cam-1", mock_settings, qualities=["medium"], dry_run=True
        )
    client_cls.assert_not_called()
    assert result["dry_run"] is True
    assert result["payload"] == {"qualities": ["medium"]}


@pytest.mark.asyncio
@pytest.mark.parametrize("qualities", [[], ["ultra"], ["high", "4k"]])
async def test_rtsps_stream_rejects_bad_qualities(mock_settings, qualities):
    from src.tools.protect_cameras import (
        create_protect_camera_rtsps_stream,
        delete_protect_camera_rtsps_stream,
    )

    with patch("src.tools.protect_cameras.ProtectClient") as client_cls:
        with pytest.raises(ValidationError):
            await create_protect_camera_rtsps_stream(
                "cam-1", mock_settings, qualities=qualities, confirm=True
            )
        with pytest.raises(ValidationError):
            await delete_protect_camera_rtsps_stream(
                "cam-1", mock_settings, qualities=qualities, confirm=True
            )
    client_cls.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("confirm", [False, "false"])
async def test_rtsps_writes_require_confirm(mock_settings, confirm):
    from src.tools.protect_cameras import (
        create_protect_camera_rtsps_stream,
        delete_protect_camera_rtsps_stream,
    )

    with patch("src.tools.protect_cameras.ProtectClient") as client_cls:
        with pytest.raises(ValidationError):
            await create_protect_camera_rtsps_stream(
                "cam-1", mock_settings, qualities=["high"], confirm=confirm
            )
        with pytest.raises(ValidationError):
            await delete_protect_camera_rtsps_stream(
                "cam-1", mock_settings, qualities=["high"], confirm=confirm
            )
    client_cls.assert_not_called()


@pytest.mark.asyncio
async def test_get_protect_camera_rtsps_streams(mock_settings, write_client):
    from src.tools.protect_cameras import get_protect_camera_rtsps_streams

    with patch("src.tools.protect_cameras.ProtectClient", return_value=write_client):
        result = await get_protect_camera_rtsps_streams("cam-1", mock_settings)

    write_client.get.assert_awaited_once_with("/integration/v1/cameras/cam-1/rtsps-stream")
    assert result == {
        "camera_id": "cam-1",
        "streams": {"high": "rtsps://h", "medium": None, "low": None, "package": None},
    }


@pytest.mark.asyncio
async def test_delete_protect_camera_rtsps_stream(mock_settings, write_client):
    from src.tools.protect_cameras import delete_protect_camera_rtsps_stream

    with patch("src.tools.protect_cameras.ProtectClient", return_value=write_client):
        result = await delete_protect_camera_rtsps_stream(
            "cam-1", mock_settings, qualities=["high", "package"], confirm=True
        )

    write_client.delete.assert_awaited_once_with(
        "/integration/v1/cameras/cam-1/rtsps-stream",
        params={"qualities": ["high", "package"]},
    )
    assert result == {"success": True, "camera_id": "cam-1", "removed": ["high", "package"]}


@pytest.mark.asyncio
async def test_delete_protect_camera_rtsps_stream_dry_run(mock_settings):
    from src.tools.protect_cameras import delete_protect_camera_rtsps_stream

    with patch("src.tools.protect_cameras.ProtectClient") as client_cls:
        result = await delete_protect_camera_rtsps_stream(
            "cam-1", mock_settings, qualities=["low"], dry_run=True
        )
    client_cls.assert_not_called()
    assert result["dry_run"] is True
    assert result["params"] == {"qualities": ["low"]}


# --------------------------------------------------------------------------- #
# Snapshot (gap P3) and PTZ (gap P4)                                          #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_get_protect_camera_snapshot_returns_base64(mock_settings):
    from src.tools.protect_cameras import get_protect_camera_snapshot

    client = AsyncMock()
    client.authenticate = AsyncMock()
    client.get_bytes = AsyncMock(return_value=(b"\xff\xd8jpeg", "image/jpeg"))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with patch("src.tools.protect_cameras.ProtectClient", return_value=client):
        result = await get_protect_camera_snapshot(
            "cam-1", mock_settings, channel="package", high_quality=True
        )

    client.get_bytes.assert_awaited_once_with(
        "/integration/v1/cameras/cam-1/snapshot",
        params={"channel": "package", "highQuality": "true"},
    )
    assert result == {
        "camera_id": "cam-1",
        "content_type": "image/jpeg",
        "size_bytes": 6,
        "image_base64": "/9hqcGVn",
    }


@pytest.mark.asyncio
async def test_get_protect_camera_snapshot_default_params(mock_settings):
    from src.tools.protect_cameras import get_protect_camera_snapshot

    client = AsyncMock()
    client.authenticate = AsyncMock()
    client.get_bytes = AsyncMock(return_value=(b"x", "image/jpeg"))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with patch("src.tools.protect_cameras.ProtectClient", return_value=client):
        await get_protect_camera_snapshot("cam-1", mock_settings)

    client.get_bytes.assert_awaited_once_with("/integration/v1/cameras/cam-1/snapshot", params={})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool", "kwargs", "path"),
    [
        ("goto_protect_camera_ptz_preset", {"slot": -1}, "cameras/cam-1/ptz/goto/-1"),
        ("goto_protect_camera_ptz_preset", {"slot": 3}, "cameras/cam-1/ptz/goto/3"),
        ("start_protect_camera_ptz_patrol", {"slot": 0}, "cameras/cam-1/ptz/patrol/start/0"),
        ("stop_protect_camera_ptz_patrol", {}, "cameras/cam-1/ptz/patrol/stop"),
    ],
)
async def test_ptz_actions_post_spec_path(mock_settings, write_client, tool, kwargs, path):
    import src.tools.protect_cameras as module

    write_client.post = AsyncMock(return_value=None)
    with patch("src.tools.protect_cameras.ProtectClient", return_value=write_client):
        result = await getattr(module, tool)("cam-1", mock_settings, confirm=True, **kwargs)

    write_client.post.assert_awaited_once_with(f"/integration/v1/{path}")
    assert result["success"] is True
    assert result["camera_id"] == "cam-1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool", "kwargs"),
    [
        ("goto_protect_camera_ptz_preset", {"slot": -2}),
        ("start_protect_camera_ptz_patrol", {"slot": 5}),
        ("start_protect_camera_ptz_patrol", {"slot": -1}),
    ],
)
async def test_ptz_rejects_bad_slot(mock_settings, tool, kwargs):
    import src.tools.protect_cameras as module

    with patch("src.tools.protect_cameras.ProtectClient") as client_cls:
        with pytest.raises(ValidationError):
            await getattr(module, tool)("cam-1", mock_settings, confirm=True, **kwargs)
    client_cls.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool", "kwargs"),
    [
        ("goto_protect_camera_ptz_preset", {"slot": 1}),
        ("start_protect_camera_ptz_patrol", {"slot": 1}),
        ("stop_protect_camera_ptz_patrol", {}),
    ],
)
async def test_ptz_requires_confirm_and_dry_run_makes_no_call(mock_settings, tool, kwargs):
    import src.tools.protect_cameras as module

    fn = getattr(module, tool)
    with patch("src.tools.protect_cameras.ProtectClient") as client_cls:
        with pytest.raises(ValidationError):
            await fn("cam-1", mock_settings, confirm="false", **kwargs)
        preview = await fn("cam-1", mock_settings, dry_run=True, **kwargs)
    client_cls.assert_not_called()
    assert preview["dry_run"] is True
    assert preview["operation"] == tool
