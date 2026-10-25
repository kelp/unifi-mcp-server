"""UniFi Protect camera model."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProtectCamera(BaseModel):
    """UniFi Protect camera details (Protect integration API 7.3.70 shape)."""

    id: str = Field(..., description="Camera identifier")
    name: str | None = Field(None, description="Camera name")
    model: str | None = Field(None, description="Camera model (from spec ``type``)")
    type: str | None = Field(None, description="Device model name")
    model_key: str | None = Field(None, alias="modelKey", description="Model key")
    state: str | None = Field(None, description="CONNECTED, CONNECTING or DISCONNECTED")
    guid: str | None = Field(None, description="Stable identifier for the device model")
    mac: str | None = Field(None, description="Camera MAC address")
    is_mic_enabled: bool | None = Field(None, alias="isMicEnabled", description="Mic enabled")
    mic_volume: float | None = Field(None, alias="micVolume", description="Mic volume 0-100")
    osd_settings: dict[str, Any] | None = Field(None, alias="osdSettings")
    led_settings: dict[str, Any] | None = Field(None, alias="ledSettings")
    lcd_message: dict[str, Any] | None = Field(None, alias="lcdMessage")
    active_patrol_slot: int | None = Field(None, alias="activePatrolSlot")
    video_mode: str | None = Field(None, alias="videoMode")
    hdr_type: str | None = Field(None, alias="hdrType")
    has_package_camera: bool | None = Field(None, alias="hasPackageCamera")
    smart_detect_settings: dict[str, Any] | None = Field(None, alias="smartDetectSettings")
    feature_flags: dict[str, Any] | None = Field(None, alias="featureFlags")
    has_speaker: bool | None = Field(
        None, alias="hasSpeaker", description="Speaker present (from featureFlags.hasSpeaker)"
    )
    has_mic: bool | None = Field(
        None, alias="hasMic", description="Microphone present (from featureFlags.hasMic)"
    )
    # Not in the 7.3.70 integration spec; kept for older firmware, else null.
    is_recording: bool | None = Field(
        None, alias="isRecording", description="Recording enabled (not in 7.3.70 spec)"
    )
    can_ptz: bool | None = Field(
        None, alias="canPtz", description="PTZ supported (not in 7.3.70 spec)"
    )
    firmware_version: str | None = Field(
        None, alias="firmwareVersion", description="Firmware version (not in 7.3.70 spec)"
    )

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    @model_validator(mode="before")
    @classmethod
    def _map_spec_fields(cls, data: Any) -> Any:
        """Fill ``model``, ``hasMic`` and ``hasSpeaker`` from the spec fields."""
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if data.get("model") is None and data.get("type") is not None:
            data["model"] = data["type"]
        flags = data.get("featureFlags")
        if isinstance(flags, dict):
            for key in ("hasMic", "hasSpeaker"):
                if data.get(key) is None and key in flags:
                    data[key] = flags[key]
        return data
