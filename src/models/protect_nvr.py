"""UniFi Protect NVR model."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProtectNVR(BaseModel):
    """UniFi Protect NVR details (Protect integration API 7.3.70 shape)."""

    id: str = Field(..., description="NVR identifier")
    name: str | None = Field(None, description="NVR name")
    model_key: str | None = Field(None, alias="modelKey", description="Model key")
    type: str | None = Field(None, description="NVR model name")
    guid: str | None = Field(None, description="NVR GUID")
    mac: str | None = Field(None, description="Primary MAC address")
    doorbell_settings: dict[str, Any] | None = Field(None, alias="doorbellSettings")
    arm_mode: dict[str, Any] | None = Field(None, alias="armMode")
    model: str | None = Field(None, description="NVR model")
    state: str | None = Field(None, description="NVR state")
    host: str | None = Field(None, description="NVR host")
    version: str | None = Field(None, alias="firmwareVersion", description="Firmware version")
    uptime: int | None = Field(None, description="Uptime in seconds")

    model_config = ConfigDict(populate_by_name=True)
