"""Which mode this PC runs in, read from lan.json. No file means Single PC (today's behaviour)."""

import ipaddress
import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class LanConfigError(ValueError):
    """The configuration cannot be trusted; a Main PC must refuse to start."""


def lan_dir() -> Path:
    """Folder holding lan.json, the CA and the keys. Restricted to SYSTEM and Administrators by `harden`."""
    override = os.environ.get("PPERP_LAN_DIR")
    if override:
        return Path(override)
    return Path(os.environ.get("ProgramData") or "C:/ProgramData") / "PetrolPumpERP" / "lan"


class LanConfig(BaseModel):
    mode: Literal["single", "main"] = "single"
    bind_address: str = ""
    port: int = Field(default=8443, ge=1024, le=65535)
    pairing_port: int = Field(default=8444, ge=1024, le=65535)
    allowed_subnets: list[str] = Field(default_factory=list)
    server_names: list[str] = Field(default_factory=list)  # extra host names for the server certificate
    max_body_bytes: int = Field(default=2_000_000, ge=10_000, le=50_000_000)
    requests_per_minute: int = Field(default=600, ge=10, le=100_000)

    @field_validator("allowed_subnets")
    @classmethod
    def _subnets(cls, value: list[str]) -> list[str]:
        return [str(ipaddress.ip_network(v, strict=False)) for v in value]

    def validate_for_main(self) -> None:
        """Every check a Main PC needs before it opens a port. Raises LanConfigError."""
        if self.mode != "main":
            raise LanConfigError("This PC is not set up as the Main PC.")
        try:
            ip = ipaddress.ip_address(self.bind_address)
        except ValueError:
            raise LanConfigError("Choose the Main PC's own network address (for example 192.168.1.10); a name or blank will not do.")
        if ip.is_unspecified or ip.is_multicast:
            raise LanConfigError("The Main PC must listen on one chosen address, not on every network card (0.0.0.0).")
        if not ip.is_private:
            raise LanConfigError("The Main PC may only listen on a private (office/shop) network address.")
        if self.port == self.pairing_port:
            raise LanConfigError("The enrolment port must differ from the main port.")
        if not self.allowed_subnets:
            raise LanConfigError("List at least one allowed network (for example 192.168.1.0/24).")
        for net_text in self.allowed_subnets:
            net = ipaddress.ip_network(net_text)
            if not net.is_private or net.prefixlen < 16:
                raise LanConfigError(f"{net_text} is too wide or not a private network; use something like 192.168.1.0/24.")


def load(path: Path | None = None) -> LanConfig:
    path = path or lan_dir() / "lan.json"
    if not path.exists():
        return LanConfig()
    try:
        return LanConfig.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except Exception as exc:  # a broken file must not silently become Single PC mode on a Main PC
        raise LanConfigError(f"lan.json is unreadable: {exc}") from exc


def save(config: LanConfig, path: Path | None = None) -> Path:
    path = path or lan_dir() / "lan.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(config.model_dump_json(indent=2), encoding="utf-8")
    return path
