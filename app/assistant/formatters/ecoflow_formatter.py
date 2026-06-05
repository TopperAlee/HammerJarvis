from typing import Any

from app.assistant.llm_client import sanitize_german_answer


def format_ecoflow_energy_answer(tool_result: dict[str, Any]) -> str:
    human_status = tool_result.get("human_status") if isinstance(tool_result, dict) else {}
    if not isinstance(human_status, dict):
        human_status = {}

    headline = str(
        human_status.get("headline")
        or tool_result.get("summary")
        or "EcoFlow Energieuebersicht ist verfuegbar."
    ).strip()
    lines = [headline]

    details = human_status.get("details", [])
    if isinstance(details, list):
        lines.extend(f"- {_round_text_numbers(str(detail))}" for detail in details if str(detail).strip())

    battery_line = _battery_power_line(tool_result)
    if battery_line and not _contains_label(lines, "Batterieleistung roh"):
        lines.append(f"- {battery_line}")

    warning_messages = _warning_messages(tool_result)[:3]
    if warning_messages:
        lines.append("")
        lines.append("Hinweise:")
        lines.extend(f"- {message}" for message in warning_messages)

    direction_note = _battery_direction_note(tool_result)
    if direction_note:
        lines.append("")
        lines.append(direction_note)

    return sanitize_german_answer("\n".join(line for line in lines if line is not None))


def _battery_power_line(tool_result: dict[str, Any]) -> str | None:
    raw_value = _battery_raw_value(tool_result)
    if raw_value is None:
        return None
    return f"Batterieleistung roh: {_format_number(raw_value)} W"


def _battery_direction_note(tool_result: dict[str, Any]) -> str | None:
    battery_status = tool_result.get("battery_status", {})
    if not isinstance(battery_status, dict):
        return None

    sign_convention = str(battery_status.get("sign_convention") or "unknown")
    raw_value = _battery_raw_value(tool_result)
    if raw_value is None and "sign_convention" not in battery_status:
        return None
    if sign_convention == "unknown":
        return "Die Richtung wird noch nicht interpretiert."
    if raw_value is None:
        return None

    if abs(raw_value) <= 20:
        return "Die Batterieleistung liegt nahe 0 W."
    if sign_convention == "positive_charging":
        direction = "laedt" if raw_value > 20 else "entlaedt"
    elif sign_convention == "negative_charging":
        direction = "laedt" if raw_value < -20 else "entlaedt"
    else:
        return "Die Richtung wird noch nicht interpretiert."
    return f"Die Batterie {direction} mit {_format_number(abs(raw_value))} W."


def _battery_raw_value(tool_result: dict[str, Any]) -> float | None:
    battery_status = tool_result.get("battery_status", {})
    if isinstance(battery_status, dict):
        value = _to_float(battery_status.get("raw_value_w"))
        if value is not None:
            return value

    battery_power = tool_result.get("battery_power")
    if isinstance(battery_power, dict):
        value = _to_float(battery_power.get("value"))
        if value is not None:
            return value

    return _to_float(tool_result.get("battery_power_w"))


def _warning_messages(tool_result: dict[str, Any]) -> list[str]:
    messages: list[str] = []
    warnings = tool_result.get("warnings", [])
    if not isinstance(warnings, list):
        return messages
    for warning in warnings:
        if isinstance(warning, dict):
            message = str(warning.get("message") or "").strip()
        else:
            message = str(warning).strip()
        if message:
            messages.append(_round_text_numbers(message))
    return messages


def _round_text_numbers(text: str) -> str:
    labels = (" W", " %", " Wh")
    if not any(label in text for label in labels):
        return text

    words = text.split()
    rounded: list[str] = []
    for index, word in enumerate(words):
        next_word = words[index + 1] if index + 1 < len(words) else ""
        value = _to_float(word.rstrip(".,;:"))
        if value is not None and next_word in {"W", "%", "Wh"}:
            suffix = word[len(word.rstrip(".,;:")) :]
            rounded.append(f"{_format_number(value)}{suffix}")
        else:
            rounded.append(word)
    return " ".join(rounded)


def _format_number(value: float) -> str:
    if value == 0:
        value = 0.0
    return str(int(round(value)))


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _contains_label(lines: list[str], label: str) -> bool:
    return any(label.lower() in line.lower() for line in lines)
