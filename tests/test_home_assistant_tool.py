from datetime import datetime, timedelta, timezone

import pytest

from app.agent.permissions import (
    ActionRisk,
    classify_action,
    is_confirmation_required,
)
from app.config.entity_overrides import load_entity_overrides
from app.tools.home_assistant import HomeAssistantTool


def test_permission_classification_works() -> None:
    assert classify_action("get_all_states") == ActionRisk.GREEN
    assert classify_action("search_entities") == ActionRisk.GREEN
    assert classify_action("turn_on") == ActionRisk.YELLOW
    assert classify_action("plc_write") == ActionRisk.RED
    assert classify_action("delete_files") == ActionRisk.RED
    assert classify_action("send_email") == ActionRisk.RED
    assert is_confirmation_required("turn_off") is True
    assert is_confirmation_required("get_entity_state") is False


def test_get_unavailable_entities_filters_problem_states(monkeypatch) -> None:
    tool = HomeAssistantTool()

    monkeypatch.setattr(
        tool,
        "get_all_states",
        lambda: [
            {"entity_id": "sensor.ok", "state": "12"},
            {"entity_id": "sensor.bad", "state": "unavailable"},
            {"entity_id": "sensor.unknown", "state": "unknown"},
        ],
    )

    result = tool.get_unavailable_entities()

    assert [item["entity_id"] for item in result] == [
        "sensor.bad",
        "sensor.unknown",
    ]


def test_get_problem_entities_classifies_home_assistant_noise(monkeypatch) -> None:
    tool = HomeAssistantTool()

    monkeypatch.setattr(
        tool,
        "get_all_states",
        lambda: [
            {"entity_id": "sensor.temperature", "state": "unavailable"},
            {"entity_id": "light.kitchen", "state": "unknown"},
            {"entity_id": "button.restart", "state": "unknown"},
            {"entity_id": "event.doorbell", "state": "unknown"},
            {"entity_id": "notify.mobile_app", "state": "unknown"},
            {"entity_id": "tts.piper", "state": "unknown"},
            {"entity_id": "conversation.home_assistant", "state": "unknown"},
            {
                "entity_id": "button.front_camera_reboot",
                "state": "unavailable",
                "attributes": {"friendly_name": "Front Camera Reboot"},
            },
            {"entity_id": "sensor.ok", "state": "23"},
        ],
    )

    result = tool.get_problem_entities()

    assert result["critical_count"] == 1
    assert result["warning_count"] == 2
    assert result["informational_count"] == 5
    assert [item["entity_id"] for item in result["critical"]] == [
        "sensor.temperature"
    ]
    assert [item["entity_id"] for item in result["warning"]] == [
        "light.kitchen",
        "button.front_camera_reboot",
    ]
    assert [item["entity_id"] for item in result["informational"]] == [
        "button.restart",
        "event.doorbell",
        "notify.mobile_app",
        "tts.piper",
        "conversation.home_assistant",
    ]


def test_get_problem_entities_never_classifies_button_unknown_as_critical(
    monkeypatch,
) -> None:
    tool = HomeAssistantTool()

    monkeypatch.setattr(
        tool,
        "get_all_states",
        lambda: [{"entity_id": "button.camera_restart", "state": "unknown"}],
    )

    result = tool.get_problem_entities()

    assert result["critical"] == []
    assert result["warning"] == []
    assert result["informational"][0]["entity_id"] == "button.camera_restart"


def test_search_entities_checks_entity_id_and_friendly_name(monkeypatch) -> None:
    tool = HomeAssistantTool()

    monkeypatch.setattr(
        tool,
        "get_all_states",
        lambda: [
            {"entity_id": "sensor.power", "attributes": {"friendly_name": "Main"}},
            {"entity_id": "sensor.x", "attributes": {"friendly_name": "EcoFlow Akku"}},
        ],
    )

    result = tool.search_entities("ecoflow")

    assert result == [
        {"entity_id": "sensor.x", "attributes": {"friendly_name": "EcoFlow Akku"}}
    ]


def test_get_power_entities_detects_units_and_keywords(monkeypatch) -> None:
    tool = HomeAssistantTool()

    monkeypatch.setattr(
        tool,
        "get_all_states",
        lambda: [
            {
                "entity_id": "sensor.energy_today",
                "attributes": {"unit_of_measurement": "kWh"},
            },
            {
                "entity_id": "sensor.ecoflow_status",
                "attributes": {"friendly_name": "EcoFlow Status"},
            },
            {"entity_id": "sensor.temperature", "attributes": {"unit_of_measurement": "C"}},
        ],
    )

    result = tool.get_power_entities()

    assert [item["entity_id"] for item in result] == [
        "sensor.energy_today",
        "sensor.ecoflow_status",
    ]


def test_get_ecoflow_entities_filters_and_shapes_result(monkeypatch) -> None:
    tool = HomeAssistantTool()

    monkeypatch.setattr(
        tool,
        "get_all_states",
        lambda: [
            {
                "entity_id": "sensor.ecoflow_stream_ultra_soc",
                "state": "87",
                "attributes": {
                    "friendly_name": "EcoFlow Stream Ultra SOC",
                    "unit_of_measurement": "%",
                    "device_class": "battery",
                },
                "last_changed": "2026-05-31T10:00:00+00:00",
                "last_updated": "2026-05-31T10:01:00+00:00",
            },
            {
                "entity_id": "sensor.grid_power",
                "state": "120",
                "attributes": {
                    "friendly_name": "Smart Meter Leistung",
                    "unit_of_measurement": "W",
                },
                "last_changed": "2026-05-31T10:02:00+00:00",
                "last_updated": "2026-05-31T10:03:00+00:00",
            },
            {
                "entity_id": "sensor.temperature",
                "state": "22",
                "attributes": {"friendly_name": "Wohnzimmer Temperatur"},
            },
        ],
    )

    result = tool.get_ecoflow_entities()

    assert result == [
        {
            "entity_id": "sensor.ecoflow_stream_ultra_soc",
            "state": "87",
            "friendly_name": "EcoFlow Stream Ultra SOC",
            "unit_of_measurement": "%",
            "device_class": "battery",
            "last_changed": "2026-05-31T10:00:00+00:00",
            "last_updated": "2026-05-31T10:01:00+00:00",
        },
        {
            "entity_id": "sensor.grid_power",
            "state": "120",
            "friendly_name": "Smart Meter Leistung",
            "unit_of_measurement": "W",
            "device_class": None,
            "last_changed": "2026-05-31T10:02:00+00:00",
            "last_updated": "2026-05-31T10:03:00+00:00",
        },
    ]


def test_diagnose_ecoflow_classifies_unavailable_sensor_as_problem(
    monkeypatch,
) -> None:
    tool = HomeAssistantTool()

    monkeypatch.setattr(
        tool,
        "get_ecoflow_entities",
        lambda: [
            {
                "entity_id": "sensor.ecoflow_required_sensor",
                "state": "unavailable",
                "friendly_name": "EcoFlow Required Sensor",
                "unit_of_measurement": "%",
                "device_class": "battery",
                "last_changed": "2026-05-31T10:00:00+00:00",
                "last_updated": "2026-05-31T10:01:00+00:00",
            },
            {
                "entity_id": "sensor.ecoflow_output_power",
                "state": "300",
                "friendly_name": "EcoFlow Output Power",
                "unit_of_measurement": "W",
                "device_class": "power",
                "last_changed": "2026-05-31T10:02:00+00:00",
                "last_updated": "2026-05-31T10:03:00+00:00",
            },
            {
                "entity_id": "sensor.smartmeter_status",
                "state": "unknown",
                "friendly_name": "Smartmeter Status",
                "unit_of_measurement": None,
                "device_class": None,
                "last_changed": "2026-05-31T10:04:00+00:00",
                "last_updated": "2026-05-31T10:05:00+00:00",
            },
        ],
    )

    result = tool.diagnose_ecoflow()

    assert result["total"] == 3
    assert result["available_count"] == 1
    assert result["unavailable_count"] == 1
    assert result["unknown_count"] == 1
    assert [item["entity_id"] for item in result["problem_entities"]] == [
        "sensor.ecoflow_required_sensor",
        "sensor.smartmeter_status",
    ]
    assert [item["entity_id"] for item in result["power_entities"]] == [
        "sensor.ecoflow_output_power"
    ]
    assert [item["entity_id"] for item in result["battery_entities"]] == [
        "sensor.ecoflow_required_sensor"
    ]
    assert "problematisch" in result["summary"]


def test_get_ecoflow_energy_overview_extracts_values(monkeypatch) -> None:
    tool = HomeAssistantTool()

    monkeypatch.setattr(
        tool,
        "get_ecoflow_entities",
        lambda: [
            {
                "entity_id": "sensor.ecoflow_pv_gesamtleistung_system",
                "state": "493",
                "friendly_name": "PV Gesamtleistung System",
                "unit_of_measurement": "W",
                "last_updated": "2026-05-31T10:00:00+00:00",
            },
            {"entity_id": "sensor.ecoflow_netzleistung_system", "state": "-453"},
            {"entity_id": "sensor.ecoflow_lan_smart_meter", "state": "107"},
            {"entity_id": "sensor.ecoflow_batterie_leistung", "state": "453"},
            {"entity_id": "sensor.ecoflow_soc_system_master", "state": "33"},
            {"entity_id": "sensor.ecoflow_soc_ultra_x", "state": "77"},
            {"entity_id": "sensor.ecoflow_verbrauch_heute", "state": "1200"},
            {"entity_id": "sensor.ecoflow_netzbezug_heute", "state": "300"},
            {"entity_id": "sensor.ecoflow_batterieenergie_heute", "state": "900"},
            {"entity_id": "sensor.ecoflow_solarenergie_heute", "state": "2500"},
        ],
    )

    result = tool.get_ecoflow_energy_overview()

    assert result["pv_power_w"] == 493.0
    assert result["grid_power_w"] == -453.0
    assert result["smart_meter_w"] == 107.0
    assert result["battery_power_w"] == 453.0
    assert result["soc_percent"] == 33.0
    assert result["consumption_today_wh"] == 1200.0
    assert result["grid_import_today_wh"] == 300.0
    assert result["battery_energy_today_wh"] == 900.0
    assert result["solar_energy_today_wh"] == 2500.0
    assert result["pv_power"]["value"] == 493.0
    assert result["pv_power"]["unit"] == "W"
    assert (
        result["pv_power"]["source_entity_id"]
        == "sensor.ecoflow_pv_gesamtleistung_system"
    )
    assert result["pv_power"]["source_friendly_name"] == "PV Gesamtleistung System"
    assert result["pv_power"]["last_updated"] == "2026-05-31T10:00:00+00:00"
    assert "age_seconds" in result["pv_power"]
    assert "freshness" in result["pv_power"]
    assert "493 W PV-Leistung" in result["summary"]
    assert "33 %" in result["summary"]


def test_get_ecoflow_energy_overview_prefers_exact_match_over_partial(
    monkeypatch,
) -> None:
    tool = HomeAssistantTool()

    monkeypatch.setattr(
        tool,
        "get_ecoflow_entities",
        lambda: [
            {
                "entity_id": "sensor.ecoflow_pv_gesamtleistung",
                "state": "0",
                "friendly_name": "PV Gesamtleistung",
                "unit_of_measurement": "W",
                "last_updated": "partial",
            },
            {
                "entity_id": "sensor.ecoflow_pv_gesamtleistung_system",
                "state": "493",
                "friendly_name": "PV Gesamtleistung System",
                "unit_of_measurement": "W",
                "last_updated": "exact",
            },
            {"entity_id": "sensor.ecoflow_netzbezug", "state": "999"},
            {"entity_id": "sensor.ecoflow_netzleistung_system", "state": "-0.0"},
        ],
    )

    result = tool.get_ecoflow_energy_overview()

    assert result["pv_power"]["value"] == 493.0
    assert (
        result["pv_power"]["source_entity_id"]
        == "sensor.ecoflow_pv_gesamtleistung_system"
    )
    assert result["grid_power"]["value"] == 0.0
    assert (
        result["grid_power"]["source_entity_id"]
        == "sensor.ecoflow_netzleistung_system"
    )
    assert result["grid_power_w"] == 0.0


def test_get_ecoflow_energy_overview_values_include_source_entity_id(
    monkeypatch,
) -> None:
    tool = HomeAssistantTool()

    monkeypatch.setattr(
        tool,
        "get_ecoflow_entities",
        lambda: [{"entity_id": "sensor.ecoflow_lan_smart_meter", "state": "107"}],
    )

    result = tool.get_ecoflow_energy_overview()

    for key in (
        "pv_power",
        "grid_power",
        "smart_meter",
        "battery_power",
        "soc",
        "consumption_today",
        "grid_import_today",
        "battery_energy_today",
        "solar_energy_today",
    ):
        assert "source_entity_id" in result[key]


def test_get_ecoflow_energy_overview_missing_values_do_not_crash(
    monkeypatch,
) -> None:
    tool = HomeAssistantTool()

    monkeypatch.setattr(
        tool,
        "get_ecoflow_entities",
        lambda: [{"entity_id": "sensor.ecoflow_pv_gesamtleistung_system", "state": "bad"}],
    )

    result = tool.get_ecoflow_energy_overview()

    assert result["pv_power_w"] is None
    assert result["pv_power"]["value"] is None
    assert result["pv_power"]["source_entity_id"] is None
    assert result["grid_power_w"] is None
    assert result["smart_meter_w"] is None
    assert result["battery_power_w"] is None
    assert result["soc_percent"] is None
    assert result["consumption_today_wh"] is None
    assert result["grid_import_today_wh"] is None
    assert result["battery_energy_today_wh"] is None
    assert result["solar_energy_today_wh"] is None
    assert result["summary"]


def test_ecoflow_energy_overview_marks_stale_values(monkeypatch) -> None:
    tool = HomeAssistantTool()
    stale_time = (datetime.now(timezone.utc) - timedelta(seconds=1000)).isoformat()

    monkeypatch.setattr(
        tool,
        "get_ecoflow_entities",
        lambda: [
            {
                "entity_id": "sensor.ecoflow_pv_gesamtleistung_system",
                "state": "10",
                "last_updated": stale_time,
            }
        ],
    )

    result = tool.get_ecoflow_energy_overview()

    assert result["pv_power"]["freshness"] == "stale"
    assert result["pv_power"]["age_seconds"] >= 900
    assert any(warning["entity_key"] == "pv_power" for warning in result["warnings"])


def test_ecoflow_energy_overview_marks_fresh_values(monkeypatch) -> None:
    tool = HomeAssistantTool()
    fresh_time = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()

    monkeypatch.setattr(
        tool,
        "get_ecoflow_entities",
        lambda: [
            {
                "entity_id": "sensor.ecoflow_pv_gesamtleistung_system",
                "state": "10",
                "last_updated": fresh_time,
            }
        ],
    )

    result = tool.get_ecoflow_energy_overview()

    assert result["pv_power"]["freshness"] == "fresh"
    assert result["pv_power"]["age_seconds"] <= 120


def test_ecoflow_battery_status_unknown_sign_does_not_interpret(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ECOFLOW_BATTERY_POWER_SIGN", "unknown")
    tool = HomeAssistantTool()

    monkeypatch.setattr(
        tool,
        "get_ecoflow_entities",
        lambda: [{"entity_id": "sensor.ecoflow_batterie_leistung", "state": "453"}],
    )

    result = tool.get_ecoflow_energy_overview()

    assert result["battery_status"] == {
        "raw_value_w": 453.0,
        "sign_convention": "unknown",
        "interpretation": "unknown_charge_direction",
    }
    assert "laedt" not in result["summary"]
    assert "entlaedt" not in result["summary"]


def test_ecoflow_battery_status_positive_charging(monkeypatch) -> None:
    monkeypatch.setenv("ECOFLOW_BATTERY_POWER_SIGN", "positive_charging")
    tool = HomeAssistantTool()

    monkeypatch.setattr(
        tool,
        "get_ecoflow_entities",
        lambda: [{"entity_id": "sensor.ecoflow_batterie_leistung", "state": "453"}],
    )

    result = tool.get_ecoflow_energy_overview()

    assert result["battery_status"]["interpretation"] == "charging"


def test_ecoflow_battery_status_negative_charging(monkeypatch) -> None:
    monkeypatch.setenv("ECOFLOW_BATTERY_POWER_SIGN", "negative_charging")
    tool = HomeAssistantTool()

    monkeypatch.setattr(
        tool,
        "get_ecoflow_entities",
        lambda: [{"entity_id": "sensor.ecoflow_batterie_leistung", "state": "-453"}],
    )

    result = tool.get_ecoflow_energy_overview()

    assert result["battery_status"]["interpretation"] == "charging"


def test_ecoflow_energy_warns_when_grid_and_smart_meter_differ(
    monkeypatch,
) -> None:
    tool = HomeAssistantTool()

    monkeypatch.setattr(
        tool,
        "get_ecoflow_entities",
        lambda: [
            {"entity_id": "sensor.ecoflow_netzleistung_system", "state": "130"},
            {"entity_id": "sensor.ecoflow_lan_smart_meter", "state": "6"},
        ],
    )

    result = tool.get_ecoflow_energy_overview()

    assert any(warning["code"] == "grid_smart_meter_mismatch" for warning in result["warnings"])


def test_ecoflow_energy_warning_for_stale_consumption_today_is_german_object(
    monkeypatch,
) -> None:
    tool = HomeAssistantTool()
    stale_time = (datetime.now(timezone.utc) - timedelta(seconds=1000)).isoformat()

    monkeypatch.setattr(
        tool,
        "get_ecoflow_entities",
        lambda: [
            {
                "entity_id": "sensor.ecoflow_verbrauch_heute",
                "state": "1200",
                "last_updated": stale_time,
            }
        ],
    )

    result = tool.get_ecoflow_energy_overview()

    assert result["warning_count"] == 1
    assert result["warnings"][0] == {
        "code": "stale_value",
        "severity": "warning",
        "message": "Der Tageswert Verbrauch heute ist veraltet.",
        "entity_key": "consumption_today",
        "source_entity_id": "sensor.ecoflow_verbrauch_heute",
    }


def test_ecoflow_energy_human_status_warning_when_stale_values_exist(
    monkeypatch,
) -> None:
    tool = HomeAssistantTool()
    stale_time = (datetime.now(timezone.utc) - timedelta(seconds=1000)).isoformat()

    monkeypatch.setattr(
        tool,
        "get_ecoflow_entities",
        lambda: [
            {
                "entity_id": "sensor.ecoflow_verbrauch_heute",
                "state": "1200",
                "last_updated": stale_time,
            }
        ],
    )

    result = tool.get_ecoflow_energy_overview()

    assert result["human_status"]["overall"] == "warning"
    assert "veraltet" in result["human_status"]["headline"]


def test_ecoflow_energy_human_status_critical_when_entity_unavailable(
    monkeypatch,
) -> None:
    tool = HomeAssistantTool()

    monkeypatch.setattr(
        tool,
        "get_ecoflow_entities",
        lambda: [
            {
                "entity_id": "sensor.ecoflow_required_sensor",
                "state": "unavailable",
            }
        ],
    )

    result = tool.get_ecoflow_energy_overview()

    assert result["human_status"]["overall"] == "critical"
    assert result["warnings"][0]["severity"] == "critical"
    assert (
        result["warnings"][0]["message"]
        == "EcoFlow-Entity nicht verfuegbar: sensor.ecoflow_required_sensor"
    )


def test_ignored_unavailable_entity_does_not_make_overall_critical(
    monkeypatch,
) -> None:
    tool = HomeAssistantTool()

    monkeypatch.setattr(
        tool,
        "get_ecoflow_entities",
        lambda: [
            {
                "entity_id": "sensor.ecoflow_stream_ultra_x_0525_soc_ac_pro",
                "state": "unavailable",
            }
        ],
    )

    result = tool.get_ecoflow_energy_overview()

    assert result["human_status"]["overall"] == "ok"
    assert result["critical_count"] == 0


def test_ignored_unavailable_entity_creates_info_warning(monkeypatch) -> None:
    tool = HomeAssistantTool()

    monkeypatch.setattr(
        tool,
        "get_ecoflow_entities",
        lambda: [
            {
                "entity_id": "sensor.ecoflow_stream_ultra_x_0525_soc_ac_pro",
                "state": "unavailable",
            }
        ],
    )

    result = tool.get_ecoflow_energy_overview()

    assert result["info_count"] == 1
    assert result["warnings"][0] == {
        "code": "entity_ignored",
        "severity": "info",
        "message": (
            "Bekannte optionale EcoFlow-Entity ignoriert: "
            "sensor.ecoflow_stream_ultra_x_0525_soc_ac_pro"
        ),
        "entity_key": None,
        "source_entity_id": "sensor.ecoflow_stream_ultra_x_0525_soc_ac_pro",
    }


def test_non_ignored_unavailable_entity_still_makes_overall_critical(
    monkeypatch,
) -> None:
    tool = HomeAssistantTool()

    monkeypatch.setattr(
        tool,
        "get_ecoflow_entities",
        lambda: [{"entity_id": "sensor.ecoflow_required_sensor", "state": "unavailable"}],
    )

    result = tool.get_ecoflow_energy_overview()

    assert result["human_status"]["overall"] == "critical"
    assert result["critical_count"] == 1


def test_missing_entity_overrides_json_does_not_crash(tmp_path) -> None:
    result = load_entity_overrides(tmp_path / "missing.json")

    assert result == {"ignored_entities": [], "downgraded_entities": []}


def test_invalid_entity_overrides_json_does_not_crash(tmp_path) -> None:
    invalid_file = tmp_path / "entity_overrides.json"
    invalid_file.write_text("{not valid json", encoding="utf-8")

    result = load_entity_overrides(invalid_file)

    assert result == {"ignored_entities": [], "downgraded_entities": []}


def test_ecoflow_energy_summary_rounds_values(monkeypatch) -> None:
    tool = HomeAssistantTool()

    monkeypatch.setattr(
        tool,
        "get_ecoflow_entities",
        lambda: [
            {"entity_id": "sensor.ecoflow_soc_system_master", "state": "32.4"},
            {"entity_id": "sensor.ecoflow_pv_gesamtleistung_system", "state": "0.1"},
            {"entity_id": "sensor.ecoflow_lan_smart_meter", "state": "6.4"},
            {"entity_id": "sensor.ecoflow_netzleistung_system", "state": "160.598"},
            {"entity_id": "sensor.ecoflow_batterie_leistung", "state": "-176.598"},
        ],
    )

    result = tool.get_ecoflow_energy_overview()

    assert "32 %" in result["summary"]
    assert "nahe 0 W" in result["summary"]
    assert "LAN Smart Meter: 6 W" in result["human_status"]["details"]
    assert "ca. 161 W" in result["summary"]
    assert "-177 W" in result["summary"]
    assert "160.598" not in result["summary"]
    assert "-176.598" not in result["summary"]


def test_missing_home_assistant_config_raises_clear_error(monkeypatch) -> None:
    monkeypatch.delenv("HOME_ASSISTANT_URL", raising=False)
    monkeypatch.delenv("HOME_ASSISTANT_TOKEN", raising=False)

    tool = HomeAssistantTool()

    with pytest.raises(RuntimeError, match="HOME_ASSISTANT_URL"):
        tool.get_all_states()
