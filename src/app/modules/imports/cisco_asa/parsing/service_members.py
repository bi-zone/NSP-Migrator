from __future__ import annotations

_PORT_OPERATORS = frozenset({"eq", "range", "lt", "gt", "neq"})


def _parse_directional_port_clause(
    parts: list[str],
    *,
    direction: str,
) -> dict:
    lowered = [part.lower() for part in parts]
    if direction not in lowered:
        return {}

    direction_idx = lowered.index(direction)
    if direction_idx + 1 >= len(parts):
        return {"raw": " ".join(parts)}

    operator = lowered[direction_idx + 1]
    if operator not in _PORT_OPERATORS:
        return {"raw": " ".join(parts)}

    value_idx = direction_idx + 2
    if operator == "range":
        if value_idx + 1 >= len(parts):
            return {"raw": " ".join(parts)}
        return {
            f"{direction}_op": operator,
            f"{direction}_port_from": parts[value_idx],
            f"{direction}_port_to": parts[value_idx + 1],
        }

    if value_idx >= len(parts):
        return {"raw": " ".join(parts)}
    return {
        f"{direction}_op": operator,
        f"{direction}_port": parts[value_idx],
    }


def parse_inline_service_object(raw: str) -> dict | None:  # noqa: C901
    parts = raw.split()
    if not parts:
        return None

    proto = parts[0].lower()
    if proto in {"tcp", "udp", "tcp-udp"}:
        lowered = [p.lower() for p in parts]
        payload: dict = {"protocol": proto}

        has_direction = "source" in lowered or "destination" in lowered
        if has_direction:
            payload.update(_parse_directional_port_clause(parts, direction="source"))
            payload.update(
                _parse_directional_port_clause(parts, direction="destination")
            )
            return payload

        operator_idx = next(
            (idx for idx, token in enumerate(lowered) if token in _PORT_OPERATORS),
            None,
        )
        if operator_idx is None:
            if len(parts) > 1:
                payload["raw"] = raw
            return payload

        operator = lowered[operator_idx]
        value_idx = operator_idx + 1
        payload["op"] = operator
        if operator == "range":
            if value_idx + 1 >= len(parts):
                payload["raw"] = raw
                return payload
            payload["port_from"] = parts[value_idx]
            payload["port_to"] = parts[value_idx + 1]
        elif value_idx < len(parts):
            payload["port"] = parts[value_idx]
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
