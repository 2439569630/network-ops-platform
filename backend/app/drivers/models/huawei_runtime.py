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
        pattern = re.compile(
            r"^(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\d+)\s+(\d+)\s*$",
            re.MULTILINE
        )
        
        for match in pattern.finditer(text):
            name, phy, proto, in_u, out_u, in_err, out_err = match.groups()
            results.append(cls(
                name=str(name or ""),
                phy_state=str(phy or "").lower(),
                protocol_state=str(proto or "").lower(),
                in_uti=str(in_u or ""),
                out_uti=str(out_u or ""),
                in_errors=str(in_err or ""),
                out_errors=str(out_err or ""),
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
class HuaweiInterfaceDetailRuntime:
    name: str
    phy_state: str
    protocol_state: str
    description: Optional[str]
    mtu: Optional[int]
    ip_address: Optional[str]
    mac_address: Optional[str]
    port_mode: Optional[str]
    speed: Optional[str]
    duplex: Optional[str]
    negotiation: Optional[str]
    mdi: Optional[str]
    loopback: Optional[str]
    last_line_protocol_up: Optional[str]
    last_phy_up: Optional[str]
    last_phy_down: Optional[str]
    current_time: Optional[str]
    input_rate_bps: Optional[int]
    input_rate_pps: Optional[int]
    output_rate_bps: Optional[int]
    output_rate_pps: Optional[int]
    input_peak_bps: Optional[int]
    input_peak_time: Optional[str]
    output_peak_bps: Optional[int]
    output_peak_time: Optional[str]
    input_unicast: Optional[int]
    input_multicast: Optional[int]
    input_broadcast: Optional[int]
    input_jumbo: Optional[int]
    input_discard: Optional[int]
    input_error: Optional[int]
    input_crc: Optional[int]
    input_giants: Optional[int]
    input_jabbers: Optional[int]
    input_throttles: Optional[int]
    input_runts: Optional[int]
    input_symbols: Optional[int]
    input_ignoreds: Optional[int]
    input_frames: Optional[int]
    output_unicast: Optional[int]
    output_multicast: Optional[int]
    output_broadcast: Optional[int]
    output_jumbo: Optional[int]
    output_discard: Optional[int]
    output_error: Optional[int]
    output_collisions: Optional[int]
    output_excessive_collisions: Optional[int]
    output_late_collisions: Optional[int]
    output_deferreds: Optional[int]
    input_util_threshold: Optional[float]
    output_util_threshold: Optional[float]
    input_utilization: Optional[float]
    output_utilization: Optional[float]
    input_packets_total: Optional[int]
    input_bytes_total: Optional[int]
    output_packets_total: Optional[int]
    output_bytes_total: Optional[int]
    raw_block: Optional[str]

    @classmethod
    def from_output(cls, output: str) -> List["HuaweiInterfaceDetailRuntime"]:
        results: List[HuaweiInterfaceDetailRuntime] = []
        text = str(output or "")
        if not text.strip():
            return results
        blocks = re.split(r"\n(?=[A-Za-z][^\n]+ current state\s*:)", text)
        for block in blocks:
            b = str(block or "")
            name = None
            phy = None
            proto = None
            m = re.search(r"^(\S+)\s+current state\s*:\s*(\S+)", b, flags=re.MULTILINE)
            if m:
                name = m.group(1)
                phy = m.group(2)
            m2 = re.search(r"Line protocol current state\s*:\s*([A-Za-z]+)", b)
            if m2:
                proto = m2.group(1)
            desc = None
            m = re.search(r"Description\s*:\s*(.+)", b)
            if m:
                desc = m.group(1).strip()
            mtu = None
            m = re.search(r"Maximum Transmit Unit is\s*(\d+)", b)
            if m:
                try:
                    mtu = int(m.group(1))
                except Exception:
                    mtu = None
            ip_addr = None
            m = re.search(r"Internet Address is\s*([0-9.]+/\d+)", b)
            if m:
                ip_addr = m.group(1).strip()
            mac = None
            m = re.search(r"Hardware address is\s*([0-9A-Fa-f-]+)", b)
            if m:
                mac = m.group(1).strip()
            port_mode = None
            m = re.search(r"Port Mode\s*:\s*([A-Za-z ]+)", b)
            if m:
                port_mode = m.group(1).strip()
            speed = None
            loopback = None
            m = re.search(r"Speed\s*:\s*([0-9A-Za-z/]+)\s*,\s*Loopback\s*:\s*([A-Za-z]+)", b)
            if m:
                speed = m.group(1).strip()
                loopback = m.group(2).strip()
            duplex = None
            negotiation = None
            m = re.search(r"Duplex\s*:\s*([A-Za-z]+)\s*,\s*Negotiation\s*:\s*([A-Za-z]+)", b)
            if m:
                duplex = m.group(1).strip()
                negotiation = m.group(2).strip()
            mdi = None
            m = re.search(r"Mdi\s*:\s*([A-Za-z]+)", b)
            if m:
                mdi = m.group(1).strip()
            last_line_up = None
            m = re.search(r"Last line protocol up time\s*:\s*(.+)", b)
            if m:
                last_line_up = m.group(1).strip()
            last_phy_up = None
            m = re.search(r"Last physical up time\s*:\s*(.+)", b)
            if m:
                last_phy_up = m.group(1).strip()
            last_phy_down = None
            m = re.search(r"Last physical down time\s*:\s*(.+)", b)
            if m:
                last_phy_down = m.group(1).strip()
            current_time = None
            m = re.search(r"Current system time\s*:\s*(.+)", b)
            if m:
                current_time = m.group(1).strip()
            in_rate_bps = None
            in_rate_pps = None
            m = re.search(r"Last 300 seconds input rate\s*(\d+)\s*bits/sec,\s*(\d+)\s*packets/sec", b)
            if m:
                try:
                    in_rate_bps = int(m.group(1))
                    in_rate_pps = int(m.group(2))
                except Exception:
                    pass
            out_rate_bps = None
            out_rate_pps = None
            m = re.search(r"Last 300 seconds output rate\s*(\d+)\s*bits/sec,\s*(\d+)\s*packets/sec", b)
            if m:
                try:
                    out_rate_bps = int(m.group(1))
                    out_rate_pps = int(m.group(2))
                except Exception:
                    pass
            in_peak_bps = None
            in_peak_time = None
            m = re.search(r"Input peak rate\s*(\d+)\s*bits/sec,Record time\s*:\s*(.+)", b)
            if m:
                try:
                    in_peak_bps = int(m.group(1))
                except Exception:
                    in_peak_bps = None
                in_peak_time = m.group(2).strip()
            out_peak_bps = None
            out_peak_time = None
            m = re.search(r"Output peak rate\s*(\d+)\s*bits/sec,Record time\s*:\s*(.+)", b)
            if m:
                try:
                    out_peak_bps = int(m.group(1))
                except Exception:
                    out_peak_bps = None
                out_peak_time = m.group(2).strip()
            iu = re.search(r"Input\s*:\s*([0-9]+)\s*packets,\s*([0-9]+)\s*bytes", b)
            ou = re.search(r"Output\s*:\s*([0-9]+)\s*packets,\s*([0-9]+)\s*bytes", b)
            in_unicast = None
            in_multicast = None
            in_broadcast = None
            in_jumbo = None
            m = re.search(r"Unicast\s*:\s*([0-9]+),\s*Multicast\s*:\s*([0-9]+)\s*\n\s*Broadcast\s*:\s*([0-9]+),\s*Jumbo\s*:\s*([0-9]+)", b)
            if m:
                in_unicast = int(m.group(1))
                in_multicast = int(m.group(2))
                in_broadcast = int(m.group(3))
                in_jumbo = int(m.group(4))
            in_discard = None
            in_error = None
            m = re.search(r"Discard\s*:\s*([0-9]+),\s*Total Error\s*:\s*([0-9]+)", b)
            if m:
                in_discard = int(m.group(1))
                in_error = int(m.group(2))
            input_misc = {
                "CRC": "input_crc",
                "Giants": "input_giants",
                "Jabbers": "input_jabbers",
                "Throttles": "input_throttles",
                "Runts": "input_runts",
                "Symbols": "input_symbols",
                "Ignoreds": "input_ignoreds",
                "Frames": "input_frames",
            }
            misc_values = {}
            for label, key in input_misc.items():
                m = re.search(rf"{label}\s*:\s*([0-9]+)", b)
                if m:
                    misc_values[key] = int(m.group(1))
            out_unicast = None
            out_multicast = None
            out_broadcast = None
            out_jumbo = None
            m = re.search(r"Output:\s*[0-9]+\s*packets,\s*[0-9]+\s*bytes\s*\n\s*Unicast\s*:\s*([0-9]+),\s*Multicast\s*:\s*([0-9]+)\s*\n\s*Broadcast\s*:\s*([0-9]+),\s*Jumbo\s*:\s*([0-9]+)", b)
            if m:
                out_unicast = int(m.group(1))
                out_multicast = int(m.group(2))
                out_broadcast = int(m.group(3))
                out_jumbo = int(m.group(4))
            out_discard = None
            out_error = None
            m = re.search(r"Discard\s*:\s*([0-9]+),\s*Total Error\s*:\s*([0-9]+)", b)
            if m:
                out_discard = int(m.group(1))
                out_error = int(m.group(2))
            out_collisions = None
            out_excessive = None
            out_late = None
            out_deferreds = None
            m = re.search(r"Collisions\s*:\s*([0-9]+),\s*ExcessiveCollisions\s*:\s*([0-9]+)\s*\n\s*Late Collisions\s*:\s*([0-9]+),\s*Deferreds\s*:\s*([0-9]+)", b)
            if m:
                out_collisions = int(m.group(1))
                out_excessive = int(m.group(2))
                out_late = int(m.group(3))
                out_deferreds = int(m.group(4))
            input_util_threshold = None
            output_util_threshold = None
            m = re.search(r"Input bandwidth utilization threshold\s*:\s*([0-9.]+)%", b)
            if m:
                input_util_threshold = float(m.group(1))
            m = re.search(r"Output bandwidth utilization threshold\s*:\s*([0-9.]+)%", b)
            if m:
                output_util_threshold = float(m.group(1))
            input_utilization = None
            output_utilization = None
            m = re.search(r"Input bandwidth utilization\s*:\s*([0-9.]+)%", b)
            if m:
                input_utilization = float(m.group(1))
            m = re.search(r"Output bandwidth utilization\s*:\s*([0-9.]+)%", b)
            if m:
                output_utilization = float(m.group(1))
            results.append(
                cls(
                    name=name or "",
                    phy_state=str(phy or "").lower(),
                    protocol_state=str(proto or "").lower(),
                    description=desc,
                    mtu=mtu,
                    ip_address=ip_addr,
                    mac_address=mac,
                    port_mode=port_mode,
                    speed=speed,
                    duplex=duplex,
                    negotiation=negotiation,
                    mdi=mdi,
                    loopback=loopback,
                    last_line_protocol_up=last_line_up,
                    last_phy_up=last_phy_up,
                    last_phy_down=last_phy_down,
                    current_time=current_time,
                    input_rate_bps=in_rate_bps,
                    input_rate_pps=in_rate_pps,
                    output_rate_bps=out_rate_bps,
                    output_rate_pps=out_rate_pps,
                    input_peak_bps=in_peak_bps,
                    input_peak_time=in_peak_time,
                    output_peak_bps=out_peak_bps,
                    output_peak_time=out_peak_time,
                    input_unicast=in_unicast,
                    input_multicast=in_multicast,
                    input_broadcast=in_broadcast,
                    input_jumbo=in_jumbo,
                    input_discard=in_discard,
                    input_error=in_error,
                    input_crc=misc_values.get("input_crc"),
                    input_giants=misc_values.get("input_giants"),
                    input_jabbers=misc_values.get("input_jabbers"),
                    input_throttles=misc_values.get("input_throttles"),
                    input_runts=misc_values.get("input_runts"),
                    input_symbols=misc_values.get("input_symbols"),
                    input_ignoreds=misc_values.get("input_ignoreds"),
                    input_frames=misc_values.get("input_frames"),
                    output_unicast=out_unicast,
                    output_multicast=out_multicast,
                    output_broadcast=out_broadcast,
                    output_jumbo=out_jumbo,
                    output_discard=out_discard,
                    output_error=out_error,
                    output_collisions=out_collisions,
                    output_excessive_collisions=out_excessive,
                    output_late_collisions=out_late,
                    output_deferreds=out_deferreds,
                    input_util_threshold=input_util_threshold,
                    output_util_threshold=output_util_threshold,
                    input_utilization=input_utilization,
                    output_utilization=output_utilization,
                    input_packets_total=int(iu.group(1)) if iu else None,
                    input_bytes_total=int(iu.group(2)) if iu else None,
                    output_packets_total=int(ou.group(1)) if ou else None,
                    output_bytes_total=int(ou.group(2)) if ou else None,
                    raw_block=b.strip() or None,
                )
            )
        return results

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "phy_state": self.phy_state,
            "protocol_state": self.protocol_state,
            "description": self.description,
            "mtu": self.mtu,
            "ip_address": self.ip_address,
            "mac_address": self.mac_address,
            "port_mode": self.port_mode,
            "speed": self.speed,
            "duplex": self.duplex,
            "negotiation": self.negotiation,
            "mdi": self.mdi,
            "loopback": self.loopback,
            "last_line_protocol_up": self.last_line_protocol_up,
            "last_phy_up": self.last_phy_up,
            "last_phy_down": self.last_phy_down,
            "current_time": self.current_time,
            "input_rate_bps": self.input_rate_bps,
            "input_rate_pps": self.input_rate_pps,
            "output_rate_bps": self.output_rate_bps,
            "output_rate_pps": self.output_rate_pps,
            "input_peak_bps": self.input_peak_bps,
            "input_peak_time": self.input_peak_time,
            "output_peak_bps": self.output_peak_bps,
            "output_peak_time": self.output_peak_time,
            "input_unicast": self.input_unicast,
            "input_multicast": self.input_multicast,
            "input_broadcast": self.input_broadcast,
            "input_jumbo": self.input_jumbo,
            "input_discard": self.input_discard,
            "input_error": self.input_error,
            "input_crc": self.input_crc,
            "input_giants": self.input_giants,
            "input_jabbers": self.input_jabbers,
            "input_throttles": self.input_throttles,
            "input_runts": self.input_runts,
            "input_symbols": self.input_symbols,
            "input_ignoreds": self.input_ignoreds,
            "input_frames": self.input_frames,
            "output_unicast": self.output_unicast,
            "output_multicast": self.output_multicast,
            "output_broadcast": self.output_broadcast,
            "output_jumbo": self.output_jumbo,
            "output_discard": self.output_discard,
            "output_error": self.output_error,
            "output_collisions": self.output_collisions,
            "output_excessive_collisions": self.output_excessive_collisions,
            "output_late_collisions": self.output_late_collisions,
            "output_deferreds": self.output_deferreds,
            "input_util_threshold": self.input_util_threshold,
            "output_util_threshold": self.output_util_threshold,
            "input_utilization": self.input_utilization,
            "output_utilization": self.output_utilization,
            "input_packets_total": self.input_packets_total,
            "input_bytes_total": self.input_bytes_total,
            "output_packets_total": self.output_packets_total,
            "output_bytes_total": self.output_bytes_total,
            "raw_block": self.raw_block,
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
