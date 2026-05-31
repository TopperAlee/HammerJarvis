from datetime import datetime, timezone
from typing import Any

import requests

from app.config.entity_overrides import is_ignored_entity
from app.config.settings import get_settings


POWER_UNITS = {"W", "kW", "Wh", "kWh"}
POWER_KEYWORDS = (
    "power",
    "energy",
    "watt",
    "strom",
    "leistung",
    "verbrauch",
    "ecoflow",
)
ECOFLOW_KEYWORDS = (
    "ecoflow",
    "stream",
    "ultra",
    "ac pro",
    "smartmeter",
    "smart meter",
)
ECOFLOW_ENERGY_SPECS = {
    "pv_power": {"unit": "W", "markers": ("pv_gesamtleistung_system", "pv_gesamtleistung")},
    "grid_power": {"unit": "W", "markers": ("netzleistung_system", "netz_leistung", "netzbezug")},
    "smart_meter": {"unit": "W", "markers": ("lan_smart_meter", "smart_meter_phase")},
    "battery_power": {"unit": "W", "markers": ("batterie_leistung",)},
    "soc": {"unit": "%", "markers": ("soc_system_master", "soc_ultra_x")},
    "consumption_today": {"unit": "Wh", "markers": ("verbrauch_heute",)},
    "grid_import_today": {"unit": "Wh", "markers": ("netzbezug_heute",)},
    "battery_energy_today": {"unit": "Wh", "markers": ("batterieenergie_heute",)},
    "solar_energy_today": {"unit": "Wh", "markers": ("solarenergie_heute",)},
}
DEVICE_PROBLEM_DOMAINS = {
    "sensor",
    "binary_sensor",
    "switch",
    "light",
    "climate",
    "cover",
    "camera",
}
INFORMATIONAL_UNKNOWN_DOMAINS = {"button", "event", "notify", "tts", "conversation"}
CAMERA_RELATED_DOMAINS = {"button", "select"}
ENERGY_LABELS = {
    "pv_power": "PV-Leistung",
    "grid_power": "Netzleistung System",
    "smart_meter": "LAN Smart Meter",
    "battery_power": "Batterieleistung",
    "soc": "Batterie",
    "consumption_today": "Verbrauch heute",
    "grid_import_today": "Netzbezug heute",
    "battery_energy_today": "Batterieenergie heute",
    "solar_energy_today": "Solarenergie heute",
}
STALE_MESSAGES = {
    "consumption_today": "Der Tageswert Verbrauch heute ist veraltet.",
    "grid_import_today": "Der Tageswert Netzbezug heute ist veraltet.",
    "battery_energy_today": "Der Tageswert Batterieenergie heute ist veraltet.",
    "solar_energy_today": "Der Tageswert Solarenergie heute ist veraltet.",
}


class HomeAssistantTool:
    def __init__(self) -> None:
        self._settings = get_settings()

    def get_all_states(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/states")

    def get_unavailable_entities(self) -> list[dict[str, Any]]:
        states = self.get_all_states()
        return [
            item
            for item in states
            if str(item.get("state", "")).lower() in {"unavailable", "unknown"}
        ]

    def get_problem_entities(self) -> dict[str, Any]:
        problems: dict[str, list[dict[str, Any]]] = {
            "critical": [],
            "warning": [],
            "informational": [],
        }
        for item in self.get_unavailable_entities():
            severity = self._classify_problem_entity(item)
            if severity:
                problems[severity].append(item)

        return {
            "critical_count": len(problems["critical"]),
            "warning_count": len(problems["warning"]),
            "informational_count": len(problems["informational"]),
            "critical": problems["critical"],
            "warning": problems["warning"],
            "informational": problems["informational"],
        }

    def get_entity_state(self, entity_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/states/{entity_id}")

    def search_entities(self, query: str) -> list[dict[str, Any]]:
        needle = query.lower()
        matches: list[dict[str, Any]] = []
        for item in self.get_all_states():
            entity_id = str(item.get("entity_id", "")).lower()
            friendly_name = str(
                item.get("attributes", {}).get("friendly_name", "")
            ).lower()
            if needle in entity_id or needle in friendly_name:
                matches.append(item)
        return matches

    def get_power_entities(self) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        for item in self.get_all_states():
            attributes = item.get("attributes", {})
            unit = attributes.get("unit_of_measurement")
            entity_id = str(item.get("entity_id", "")).lower()
            friendly_name = str(attributes.get("friendly_name", "")).lower()
            searchable = f"{entity_id} {friendly_name}"
            if unit in POWER_UNITS or any(word in searchable for word in POWER_KEYWORDS):
                matches.append(item)
        return matches

    def get_ecoflow_entities(self) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        for item in self.get_all_states():
            if not _matches_ecoflow(item):
                continue
            attributes = item.get("attributes", {})
            matches.append(
                {
                    "entity_id": item.get("entity_id"),
                    "state": item.get("state"),
                    "friendly_name": attributes.get("friendly_name"),
                    "unit_of_measurement": attributes.get("unit_of_measurement"),
                    "device_class": attributes.get("device_class"),
                    "last_changed": item.get("last_changed"),
                    "last_updated": item.get("last_updated"),
                }
            )
        return matches

    def diagnose_ecoflow(self) -> dict[str, Any]:
        entities = self.get_ecoflow_entities()
        unavailable = [
            item
            for item in entities
            if str(item.get("state", "")).lower() == "unavailable"
            and not is_ignored_entity(str(item.get("entity_id", "")))
        ]
        unknown = [
            item for item in entities if str(item.get("state", "")).lower() == "unknown"
        ]
        power_entities = [
            item for item in entities if item.get("unit_of_measurement") in POWER_UNITS
        ]
        battery_entities = [
            item
            for item in entities
            if item.get("device_class") == "battery"
            or item.get("unit_of_measurement") == "%"
        ]
        problem_entities = unavailable + unknown

        return {
            "total": len(entities),
            "available_count": len(entities) - len(problem_entities),
            "unavailable_count": len(unavailable),
            "unknown_count": len(unknown),
            "power_entities": power_entities,
            "battery_entities": battery_entities,
            "problem_entities": problem_entities,
            "summary": _build_ecoflow_summary(entities, problem_entities),
        }

    def get_ecoflow_energy_overview(self) -> dict[str, Any]:
        entities = self.get_ecoflow_entities()
        overview = {
            key: _pick_energy_value(entities, spec["unit"], spec["markers"])
            for key, spec in ECOFLOW_ENERGY_SPECS.items()
        }
        if overview["soc"]["value"] is None:
            overview["soc"] = _pick_battery_soc_value(entities)
        battery_status = _build_battery_status(
            overview["battery_power"]["value"],
            self._settings.ecoflow_battery_power_sign,
        )
        statuses = {
            "pv_status": _classify_pv_status(overview["pv_power"]["value"]),
            "grid_status": _classify_grid_status(overview["grid_power"]["value"]),
            "battery_status": battery_status,
            "smart_meter_status": _classify_smart_meter_status(
                overview["smart_meter"]["value"]
            ),
        }
        warnings = _build_ecoflow_energy_warnings(overview, entities)
        human_status = _build_human_status(overview, warnings, entities)
        severity_counts = _count_warning_severities(warnings)

        return {
            **overview,
            **statuses,
            "warnings": warnings,
            "warning_count": len(warnings),
            "critical_count": severity_counts["critical"],
            "warning_count_by_severity": severity_counts["warning"],
            "info_count": severity_counts["info"],
            "human_status": human_status,
            "pv_power_w": overview["pv_power"]["value"],
            "grid_power_w": overview["grid_power"]["value"],
            "smart_meter_w": overview["smart_meter"]["value"],
            "battery_power_w": overview["battery_power"]["value"],
            "soc_percent": overview["soc"]["value"],
            "consumption_today_wh": overview["consumption_today"]["value"],
            "grid_import_today_wh": overview["grid_import_today"]["value"],
            "battery_energy_today_wh": overview["battery_energy_today"]["value"],
            "solar_energy_today_wh": overview["solar_energy_today"]["value"],
            "summary": _build_ecoflow_energy_summary(
                overview, statuses, warnings, human_status
            ),
        }

    def turn_on(self, entity_id: str) -> dict[str, Any]:
        domain = self._domain_from_entity(entity_id)
        return self._request(
            "POST",
            f"/api/services/{domain}/turn_on",
            json_data={"entity_id": entity_id},
        )

    def turn_off(self, entity_id: str) -> dict[str, Any]:
        domain = self._domain_from_entity(entity_id)
        return self._request(
            "POST",
            f"/api/services/{domain}/turn_off",
            json_data={"entity_id": entity_id},
        )

    def _request(
        self,
        method: str,
        path: str,
        json_data: dict[str, Any] | None = None,
    ) -> Any:
        settings = self._settings.require_home_assistant()
        assert settings.home_assistant_url is not None
        assert settings.home_assistant_token is not None

        url = f"{settings.home_assistant_url.rstrip('/')}{path}"
        headers = {
            "Authorization": f"Bearer {settings.home_assistant_token}",
            "Content-Type": "application/json",
        }
        response = requests.request(
            method,
            url,
            headers=headers,
            json=json_data,
            timeout=10,
        )
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()

    @staticmethod
    def _domain_from_entity(entity_id: str) -> str:
        if "." not in entity_id:
            raise ValueError("Entity ID must include a domain, for example light.example")
        return entity_id.split(".", 1)[0]

    @staticmethod
    def _classify_problem_entity(item: dict[str, Any]) -> str | None:
        state = str(item.get("state", "")).lower()
        entity_id = str(item.get("entity_id", "")).lower()
        domain = entity_id.split(".", 1)[0] if "." in entity_id else ""

        if state == "unavailable":
            if domain in DEVICE_PROBLEM_DOMAINS:
                return "critical"
            if domain in CAMERA_RELATED_DOMAINS and _is_camera_related(item):
                return "warning"

        if state == "unknown":
            if domain in DEVICE_PROBLEM_DOMAINS:
                return "warning"
            if domain in INFORMATIONAL_UNKNOWN_DOMAINS:
                return "informational"

        return None


def _is_camera_related(item: dict[str, Any]) -> bool:
    attributes = item.get("attributes", {})
    entity_id = str(item.get("entity_id", "")).lower()
    friendly_name = str(attributes.get("friendly_name", "")).lower()
    return "camera" in f"{entity_id} {friendly_name}"


def _matches_ecoflow(item: dict[str, Any]) -> bool:
    attributes = item.get("attributes", {})
    entity_id = str(item.get("entity_id", "")).lower().replace("_", " ")
    friendly_name = str(attributes.get("friendly_name", "")).lower()
    searchable = f"{entity_id} {friendly_name}"
    return any(keyword in searchable for keyword in ECOFLOW_KEYWORDS)


def _build_ecoflow_summary(
    entities: list[dict[str, Any]],
    problem_entities: list[dict[str, Any]],
) -> str:
    total = len(entities)
    available_count = total - len(problem_entities)
    problem_count = len(problem_entities)
    summary = (
        f"Ich habe {total} EcoFlow-Entities gefunden. "
        f"{available_count} sind verfuegbar, {problem_count} sind problematisch."
    )
    if problem_entities:
        first_problem = problem_entities[0].get("entity_id", "unbekannt")
        summary += f" Kritisch ist aktuell {first_problem}."
    return summary


def _to_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed == 0:
        return 0.0
    return parsed


def _format_number(value: float) -> str:
    return str(int(round(value)))


def _empty_energy_value(unit: str) -> dict[str, Any]:
    return {
        "value": None,
        "unit": unit,
        "source_entity_id": None,
        "source_friendly_name": None,
        "last_updated": None,
        "age_seconds": None,
        "freshness": "unknown",
    }


def _energy_value_from_entity(entity: dict[str, Any], unit: str) -> dict[str, Any]:
    value = _to_float(entity.get("state"))
    if value is None:
        return _empty_energy_value(unit)
    return {
        "value": value,
        "unit": entity.get("unit_of_measurement") or unit,
        "source_entity_id": entity.get("entity_id"),
        "source_friendly_name": entity.get("friendly_name"),
        "last_updated": entity.get("last_updated"),
        **_evaluate_freshness(entity.get("last_updated")),
    }


def _pick_energy_value(
    entities: list[dict[str, Any]],
    unit: str,
    markers: tuple[str, ...],
) -> dict[str, Any]:
    for marker in markers:
        for entity in entities:
            entity_id = str(entity.get("entity_id", "")).lower()
            if marker in entity_id:
                return _energy_value_from_entity(entity, unit)
    return _empty_energy_value(unit)


def _pick_battery_soc_value(entities: list[dict[str, Any]]) -> dict[str, Any]:
    for entity in entities:
        entity_id = str(entity.get("entity_id", "")).lower()
        friendly_name = str(entity.get("friendly_name", "")).lower()
        searchable = f"{entity_id} {friendly_name}"
        if (
            "soc" in searchable
            and (
                entity.get("device_class") == "battery"
                or entity.get("unit_of_measurement") == "%"
            )
        ):
            return _energy_value_from_entity(entity, "%")
    return _empty_energy_value("%")


def _evaluate_freshness(last_updated: Any) -> dict[str, int | str | None]:
    if not last_updated:
        return {"age_seconds": None, "freshness": "unknown"}
    try:
        parsed = datetime.fromisoformat(str(last_updated).replace("Z", "+00:00"))
    except ValueError:
        return {"age_seconds": None, "freshness": "unknown"}
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    age_seconds = max(0, int((datetime.now(timezone.utc) - parsed).total_seconds()))
    if age_seconds <= 120:
        freshness = "fresh"
    elif age_seconds <= 900:
        freshness = "recent"
    else:
        freshness = "stale"
    return {"age_seconds": age_seconds, "freshness": freshness}


def _classify_pv_status(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value > 20:
        return "producing"
    return "low_or_none"


def _classify_grid_status(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value > 20:
        return "grid_import_or_consumption"
    if value < -20:
        return "grid_export_or_feed_in"
    return "near_zero"


def _classify_smart_meter_status(value: float | None) -> str:
    if value is None:
        return "unknown"
    if abs(value) <= 20:
        return "near_zero"
    if value > 20:
        return "positive_power"
    return "negative_power"


def _build_battery_status(value: float | None, sign_convention: str) -> dict[str, Any]:
    supported = {"unknown", "positive_charging", "negative_charging"}
    convention = sign_convention if sign_convention in supported else "unknown"
    interpretation = "unknown_charge_direction"
    if value is not None and convention == "positive_charging":
        if value > 20:
            interpretation = "charging"
        elif value < -20:
            interpretation = "discharging"
        else:
            interpretation = "near_zero"
    if value is not None and convention == "negative_charging":
        if value < -20:
            interpretation = "charging"
        elif value > 20:
            interpretation = "discharging"
        else:
            interpretation = "near_zero"
    return {
        "raw_value_w": value,
        "sign_convention": convention,
        "interpretation": interpretation,
    }


def _build_ecoflow_energy_warnings(
    overview: dict[str, dict[str, Any]],
    entities: list[dict[str, Any]],
) -> list[str]:
    warnings: list[dict[str, Any]] = []
    for key, value in overview.items():
        if value.get("freshness") == "stale":
            warnings.append(
                {
                    "code": "stale_value",
                    "severity": "warning",
                    "message": STALE_MESSAGES.get(
                        key, f"Der Wert {ENERGY_LABELS.get(key, key)} ist veraltet."
                    ),
                    "entity_key": key,
                    "source_entity_id": value.get("source_entity_id"),
                }
            )

    solar_value = overview["solar_energy_today"]["value"]
    pv_value = overview["pv_power"]["value"]
    pv_recent = overview["pv_power"]["freshness"] in {"fresh", "recent"}
    if solar_value == 0 and pv_value is not None and pv_value > 20 and pv_recent:
        warnings.append(
            {
                "code": "solar_energy_zero_while_pv_active",
                "severity": "warning",
                "message": "Der Tageswert Solarenergie steht auf 0 Wh, obwohl aktuell PV-Leistung gemessen wird.",
                "entity_key": "solar_energy_today",
                "source_entity_id": overview["solar_energy_today"].get("source_entity_id"),
            }
        )

    grid_value = overview["grid_power"]["value"]
    smart_value = overview["smart_meter"]["value"]
    if (
        grid_value is not None
        and smart_value is not None
        and abs(abs(grid_value) - abs(smart_value)) > 100
    ):
        warnings.append(
            {
                "code": "grid_smart_meter_mismatch",
                "severity": "warning",
                "message": "Netzleistung und LAN Smart Meter unterscheiden sich um mehr als 100 W.",
                "entity_key": "grid_power",
                "source_entity_id": overview["grid_power"].get("source_entity_id"),
            }
        )

    for entity in entities:
        if str(entity.get("state", "")).lower() == "unavailable":
            entity_id = str(entity.get("entity_id", ""))
            if is_ignored_entity(entity_id):
                warnings.append(
                    {
                        "code": "entity_ignored",
                        "severity": "info",
                        "message": f"Bekannte optionale EcoFlow-Entity ignoriert: {entity_id}",
                        "entity_key": None,
                        "source_entity_id": entity_id,
                    }
                )
                continue
            warnings.append(
                {
                    "code": "entity_unavailable",
                    "severity": "critical",
                    "message": f"EcoFlow-Entity nicht verfuegbar: {entity_id}",
                    "entity_key": None,
                    "source_entity_id": entity_id,
                }
            )
    return warnings


def _build_human_status(
    overview: dict[str, dict[str, Any]],
    warnings: list[dict[str, Any]],
    entities: list[dict[str, Any]],
) -> dict[str, Any]:
    if not entities:
        overall = "unknown"
        headline = "Ich habe keine EcoFlow-Daten gefunden."
    elif any(warning["severity"] == "critical" for warning in warnings):
        overall = "critical"
        headline = "EcoFlow hat aktuell ein kritisches Problem."
    elif any(warning["severity"] == "warning" for warning in warnings):
        overall = "warning"
        if _has_multiple_stale_day_values(warnings):
            headline = "EcoFlow laeuft, aber einige Werte sind veraltet."
        else:
            first_warning = next(
                warning for warning in warnings if warning["severity"] == "warning"
            )
            headline = f"EcoFlow laeuft, aber {first_warning['message']}"
    else:
        overall = "ok"
        headline = "EcoFlow laeuft ohne erkennbare Warnungen."

    details: list[str] = []
    if overview["soc"]["value"] is not None:
        details.append(f"Batterie: {_format_number(overview['soc']['value'])} %")
    if overview["pv_power"]["value"] is not None:
        details.append(f"PV-Leistung: {_format_number(overview['pv_power']['value'])} W")
    if overview["smart_meter"]["value"] is not None:
        details.append(
            f"LAN Smart Meter: {_format_number(overview['smart_meter']['value'])} W"
        )
    if overview["grid_power"]["value"] is not None:
        details.append(
            f"Netzleistung System: {_format_number(overview['grid_power']['value'])} W"
        )

    return {"overall": overall, "headline": headline, "details": details}


def _count_warning_severities(warnings: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "critical": sum(1 for warning in warnings if warning["severity"] == "critical"),
        "warning": sum(1 for warning in warnings if warning["severity"] == "warning"),
        "info": sum(1 for warning in warnings if warning["severity"] == "info"),
    }


def _has_multiple_stale_day_values(warnings: list[dict[str, Any]]) -> bool:
    stale_day_keys = {
        "consumption_today",
        "grid_import_today",
        "battery_energy_today",
        "solar_energy_today",
    }
    stale_days = {
        warning["entity_key"]
        for warning in warnings
        if warning["code"] == "stale_value" and warning["entity_key"] in stale_day_keys
    }
    return len(stale_days) > 1


def _build_ecoflow_energy_summary(
    overview: dict[str, dict[str, Any]],
    statuses: dict[str, Any],
    warnings: list[dict[str, Any]],
    human_status: dict[str, Any],
) -> str:
    parts: list[str] = []
    parts.append("EcoFlow ist erreichbar.")
    if overview["soc"]["value"] is not None:
        parts.append(
            f"Die Batterie steht bei {_format_number(overview['soc']['value'])} %."
        )
    if overview["pv_power"]["value"] is not None:
        if statuses["pv_status"] == "producing":
            parts.append(
                "Aktuell erzeugt EcoFlow "
                f"{_format_number(overview['pv_power']['value'])} W PV-Leistung."
            )
        else:
            parts.append("Aktuell wird keine PV-Leistung gemessen.")
    if overview["smart_meter"]["value"] is not None:
        smart_text = (
            "nahe 0 W"
            if statuses["smart_meter_status"] == "near_zero"
            else f"bei ca. {_format_number(overview['smart_meter']['value'])} W"
        )
        grid_text = None
        if overview["grid_power"]["value"] is not None:
            grid_text = f"bei ca. {_format_number(overview['grid_power']['value'])} W"
        if grid_text:
            parts.append(
                f"Der LAN Smart Meter liegt {smart_text}, die EcoFlow-Netzleistung liegt {grid_text}."
            )
        else:
            parts.append(f"Der LAN Smart Meter liegt {smart_text}.")
    elif overview["grid_power"]["value"] is not None:
        parts.append(
            f"Die EcoFlow-Netzleistung liegt bei ca. {_format_number(overview['grid_power']['value'])} W."
        )
    if overview["battery_power"]["value"] is not None:
        parts.append(
            "Batterieleistung roh: "
            f"{_format_number(overview['battery_power']['value'])} W."
        )
    if warnings:
        if _has_multiple_stale_day_values(warnings):
            parts.append("Achtung: Mehrere Werte sind veraltet.")
        else:
            actionable_warnings = [
                warning for warning in warnings if warning["severity"] != "info"
            ]
            if actionable_warnings:
                parts.append(f"Achtung: {actionable_warnings[0]['message']}")
    if len(parts) == 1:
        return human_status["headline"]
    return " ".join(parts)
