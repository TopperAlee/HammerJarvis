from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.agent.permissions import ActionRisk


@dataclass(frozen=True)
class RegisteredTool:
    name: str
    description: str
    risk: ActionRisk
    function: Callable[..., dict[str, Any]]
    parameter_schema: dict[str, Any]
    requires_confirmation: bool
