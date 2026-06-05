import json
from typing import Any


def extract_text(response: Any) -> str:
    if isinstance(response, dict):
        if isinstance(response.get("text"), str):
            return response["text"]
        output = response.get("output", [])
    else:
        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str):
            return output_text
        output = getattr(response, "output", [])

    texts: list[str] = []
    for item in output or []:
        content = _get(item, "content", [])
        for part in content or []:
            text = _get(part, "text", None)
            if text:
                texts.append(str(text))
    return "\n".join(texts).strip()


def extract_tool_calls(response: Any) -> list[dict[str, Any]]:
    if isinstance(response, dict) and "tool_calls" in response:
        return list(response.get("tool_calls") or [])

    output = response.get("output", []) if isinstance(response, dict) else getattr(response, "output", [])
    calls: list[dict[str, Any]] = []
    for item in output or []:
        item_type = _get(item, "type", "")
        if item_type not in {"function_call", "tool_call"}:
            continue
        name = _get(item, "name", "")
        arguments = _get(item, "arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments) if arguments else {}
            except json.JSONDecodeError:
                arguments = {}
        calls.append(
            {
                "id": _get(item, "call_id", _get(item, "id", "")),
                "name": name,
                "arguments": arguments or {},
            }
        )
    return calls


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)
