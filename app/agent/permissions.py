from enum import StrEnum


class ActionRisk(StrEnum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


GREEN_ACTIONS = {
    "get_all_states",
    "get_entity_state",
    "get_unavailable_entities",
    "search_entities",
    "get_power_entities",
    "ha_read",
    "ha_search",
    "ha_unavailable",
}

YELLOW_ACTIONS = {
    "turn_on",
    "turn_off",
    "ha_turn_on",
    "ha_turn_off",
}

RED_ACTIONS = {
    "plc_write",
    "delete_files",
    "delete_file",
    "send_email",
    "send_emails",
    "production_action",
}


def classify_action(action_name: str) -> ActionRisk:
    normalized = action_name.strip().lower().replace("-", "_")
    if normalized in GREEN_ACTIONS:
        return ActionRisk.GREEN
    if normalized in YELLOW_ACTIONS:
        return ActionRisk.YELLOW
    if normalized in RED_ACTIONS:
        return ActionRisk.RED
    return ActionRisk.RED


def is_confirmation_required(action_name: str) -> bool:
    return classify_action(action_name) != ActionRisk.GREEN
