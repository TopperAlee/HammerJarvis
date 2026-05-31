from app.agent.core import normalize_message


def test_normalize_message_removes_jarvis_comma() -> None:
    assert normalize_message("Jarvis, was macht EcoFlow gerade?") == (
        "was macht ecoflow gerade?"
    )


def test_normalize_message_removes_hey_jarvis() -> None:
    assert normalize_message("Hey Jarvis EcoFlow Energie") == "ecoflow energie"


def test_normalize_message_removes_okay_jarvis_colon() -> None:
    assert normalize_message("Okay Jarvis: welche Geräte haben Probleme?") == (
        "welche geräte haben probleme?"
    )


def test_normalize_message_collapses_spaces() -> None:
    assert normalize_message("  Jarvis   zeige EcoFlow  ") == "zeige ecoflow"
