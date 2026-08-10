from __future__ import annotations


def parse_inline_service_object(raw: str) -> dict | None:  # noqa: C901
    parts = raw.split()
    if not parts:
        return None

    proto = parts[0].lower()
    if proto == "tcp-udp":
        lowered = [p.lower() for p in parts]
        if "eq" in lowered:
            idx = lowered.index("eq")
            if idx + 1 < len(parts):
                return {
                    "protocol": "tcp-udp",
                    "op": "eq",
                    "port": parts[idx + 1],
                }
        return {"protocol": "tcp-udp", "raw": raw}

    if proto in {"tcp", "udp"}:
        lowered = [p.lower() for p in parts]
        payload: dict = {"protocol": proto}
        if "eq" in lowered:
            idx = lowered.index("eq")
            if idx + 1 < len(parts):
                payload["op"] = "eq"
                payload["port"] = parts[idx + 1]
        elif "range" in lowered:
            idx = lowered.index("range")
            if idx + 2 < len(parts):
                payload["op"] = "range"
                payload["port_from"] = parts[idx + 1]
                payload["port_to"] = parts[idx + 2]
        else:
            payload["raw"] = raw
        return payload

    if proto in {"icmp", "icmp6"}:
        payload = {"protocol": proto}
        if len(parts) > 1:
            payload["icmp"] = " ".join(parts[1:])
        return payload

    if proto in {"ip", "esp"}:
        return {"protocol": proto}

    return {"protocol": proto, "raw": raw}
