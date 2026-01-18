from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, List


@dataclass(frozen=True)
class HuaweiInterfaceRuntime:
    name: str
    phy_state: str
    protocol_state: str
    in_uti: str
    out_uti: str
    in_errors: str
    out_errors: str

    @classmethod
    def from_output(cls, output: str) -> List["HuaweiInterfaceRuntime"]:
        results = []
        text = str(output or "")
        # Skip header lines usually containing "Interface", "PHY", etc.
        # Regex to match: GigabitEthernet0/0/0        up    up          0%     0%          0          0
        pattern = re.compile(
            r"^(\S+)\s+([a-zA-Z*]+)\s+([a-zA-Z()]+)\s+(\d+%?)\s+(\d+%?)\s+(\d+)\s+(\d+)",
            re.MULTILINE
        )
        
        for match in pattern.finditer(text):
            name, phy, proto, in_u, out_u, in_err, out_err = match.groups()
            results.append(cls(
                name=name,
                phy_state=phy,
                protocol_state=proto,
                in_uti=in_u,
                out_uti=out_u,
                in_errors=in_err,
                out_errors=out_err
            ))
        return results

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "phy_state": self.phy_state,
            "protocol_state": self.protocol_state,
            "in_uti": self.in_uti,
            "out_uti": self.out_uti,
            "in_errors": self.in_errors,
            "out_errors": self.out_errors,
        }


@dataclass(frozen=True)
class HuaweiRouteRuntime:
    destination: str
    proto: str
    pre: str
    cost: str
    flags: str
    next_hop: str
    interface: str

    @classmethod
    def from_output(cls, output: str) -> List["HuaweiRouteRuntime"]:
        results = []
        text = str(output or "")
        # Regex to match: 127.0.0.0/8   Direct  0    0           D   127.0.0.1       InLoopBack0
        # Handling flexible spaces and potential flags with spaces
        pattern = re.compile(
            r"^\s*(\d+\.\d+\.\d+\.\d+/\d+)\s+(\S+)\s+(\d+)\s+(\d+)\s+([A-Z\s]+?)\s+(\d+\.\d+\.\d+\.\d+)\s+(\S+)",
            re.MULTILINE
        )

        for match in pattern.finditer(text):
            dest, proto, pre, cost, flags, nexthop, iface = match.groups()
            results.append(cls(
                destination=dest,
                proto=proto,
                pre=pre,
                cost=cost,
                flags=flags.strip(),
                next_hop=nexthop,
                interface=iface
            ))
        return results

    def to_dict(self) -> Dict[str, Any]:
        return {
            "destination": self.destination,
            "proto": self.proto,
            "pre": self.pre,
            "cost": self.cost,
            "flags": self.flags,
            "next_hop": self.next_hop,
            "interface": self.interface,
        }


@dataclass(frozen=True)
class HuaweiVlanRuntime:
    vlan_id: str
    type: str
    status: str
    mac_learning: str
    ports: List[str]  # Placeholder, currently just summary

    @classmethod
    def from_output(cls, output: str) -> List["HuaweiVlanRuntime"]:
        results = []
        text = str(output or "")
        # Regex to match: 1       common       enable   enable       forward   forward   forward default
        pattern = re.compile(
            r"^(\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+",
            re.MULTILINE
        )

        for match in pattern.finditer(text):
            vid, vtype, status, mac_l = match.groups()
            results.append(cls(
                vlan_id=vid,
                type=vtype,
                status=status,
                mac_learning=mac_l,
                ports=[] # Detailed ports often require 'display vlan <id>'
            ))
        return results

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vlan_id": self.vlan_id,
            "type": self.type,
            "status": self.status,
            "mac_learning": self.mac_learning,
            "ports": self.ports,
        }


@dataclass(frozen=True)
class HuaweiDisplayVersionRuntime:
    raw: str
    vendor: str = "Huawei"
    model: Optional[str] = None
    product: Optional[str] = None
    vrp_version: Optional[str] = None
    vrp_release: Optional[str] = None
    uptime: Optional[str] = None
    serial_number: Optional[str] = None

    @classmethod
    def from_output(cls, output: str) -> "HuaweiDisplayVersionRuntime":
        text = str(output or "")
        if not text.strip():
            return cls(raw="")

        model: Optional[str] = None
        product: Optional[str] = None
        vrp_version: Optional[str] = None
        vrp_release: Optional[str] = None
        uptime: Optional[str] = None

        vrp_match = re.search(
            r"VRP\s+\(R\)\s+software,\s+Version\s+([0-9.]+)\s*\(([^)]+)\)",
            text,
            flags=re.IGNORECASE,
        )
        if vrp_match:
            vrp_version = vrp_match.group(1).strip() or None
            inside = vrp_match.group(2).strip()
            parts = [p for p in re.split(r"\s+", inside) if p]
            if parts:
                if re.match(r"^AR\d+", parts[0], flags=re.IGNORECASE):
                    product = parts[0]
                for p in reversed(parts):
                    if re.match(r"^V\d+R\d+", p, flags=re.IGNORECASE):
                        vrp_release = p
                        break
        else:
            fallback = re.search(r"Version\s+([0-9.]+)", text, flags=re.IGNORECASE)
            if fallback:
                vrp_version = fallback.group(1).strip() or None

        model_match = re.search(r"Huawei\s+(AR[\w-]+)\s+Router", text, flags=re.IGNORECASE)
        if model_match:
            model = model_match.group(1).strip() or None
        if not model:
            board_match = re.search(r"Board\s+Type\s*:\s*(AR[\w-]+)", text, flags=re.IGNORECASE)
            if board_match:
                model = board_match.group(1).strip() or None

        uptime_match = re.search(r"Router uptime is\s+(.+)", text, flags=re.IGNORECASE)
        if uptime_match:
            uptime = uptime_match.group(1).strip() or None
        else:
            uptime_match_2 = re.search(r"uptime is\s+(.+)", text, flags=re.IGNORECASE)
            if uptime_match_2:
                uptime = uptime_match_2.group(1).strip() or None

        return cls(
            raw=text,
            vendor="Huawei",
            model=model,
            product=product,
            vrp_version=vrp_version,
            vrp_release=vrp_release,
            uptime=uptime,
        )

    def to_dict(self) -> Dict[str, Any]:
        if not str(self.raw or "").strip():
            return {}
        os_version = str(self.vrp_release or self.vrp_version or "").strip() or None
        data: Dict[str, Any] = {
            "version_raw": self.raw,
            "vendor": self.vendor,
        }
        if self.model:
            data["model"] = self.model
        if self.product:
            data["product"] = self.product
        if self.vrp_version:
            data["vrp_version"] = self.vrp_version
        if self.vrp_release:
            data["vrp_release"] = self.vrp_release
        if os_version:
            data["os_version"] = os_version
            data["version"] = os_version
        if self.uptime:
            data["uptime"] = self.uptime
        if self.serial_number:
            data["serial_number"] = self.serial_number
        return data
