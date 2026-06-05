import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.agent.permissions import ActionRisk
from app.assistant.priority_engine import PriorityEngine
from app.assistant.tool_registry import ToolRegistry
from app.logging_utils.audit import write_audit_log


DEFAULT_RULES_FILE = Path("app/config/watcher_rules.json")
DEFAULT_ALERTS_FILE = Path("app/data/watchers/alerts.json")


class WatcherController:
    def __init__(
        self,
        registry: ToolRegistry | None = None,
        rules_file: Path | None = None,
        alerts_file: Path | None = None,
    ) -> None:
        self.registry = registry or ToolRegistry()
        self.rules_file = rules_file or Path(os.getenv("WATCHER_RULES_FILE", str(DEFAULT_RULES_FILE)))
        self.alerts_file = alerts_file or Path(os.getenv("WATCHER_ALERTS_FILE", str(DEFAULT_ALERTS_FILE)))
        self.last_run: str | None = None

    def load_rules(self) -> dict[str, Any]:
        try:
            with self.rules_file.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError):
            return {"rules": []}
        if not isinstance(data, dict) or not isinstance(data.get("rules"), list):
            return {"rules": []}
        return {"rules": [rule for rule in data["rules"] if isinstance(rule, dict)]}

    def save_rules(self, rules: dict[str, Any]) -> dict[str, Any]:
        self.rules_file.parent.mkdir(parents=True, exist_ok=True)
        with self.rules_file.open("w", encoding="utf-8") as file:
            json.dump(rules, file, ensure_ascii=False, indent=2)
            file.write("\n")
        return rules

    def run_once(self) -> dict[str, Any]:
        self.last_run = _now_iso()
        write_audit_log("watchers_run_start", {})
        created: list[dict[str, Any]] = []
        suppressed: list[dict[str, Any]] = []
        for rule in self.load_rules()["rules"]:
            if not rule.get("enabled", True):
                continue
            result = self._evaluate_rule(rule)
            if not result:
                continue
            if result.get("status") == "suppressed_by_cooldown":
                suppressed.append(result)
            elif result.get("alert"):
                created.append(result["alert"])
        write_audit_log(
            "watchers_run_end",
            {"created_count": len(created), "suppressed_count": len(suppressed)},
        )
        return {
            "ran_at": self.last_run,
            "created_count": len(created),
            "suppressed_count": len(suppressed),
            "alerts": created,
            "suppressed": suppressed,
        }

    def evaluate_ecoflow_low_battery(self, rule: dict[str, Any]) -> dict[str, Any] | None:
        result = self._execute_green("ecoflow_energy_overview")
        overview = result.get("result", {})
        soc = _to_float(overview.get("soc_percent"))
        threshold = _to_float(rule.get("threshold_percent")) or 20.0
        if soc is None or soc > threshold:
            return None
        return self.add_alert(
            _alert(
                rule,
                title="EcoFlow-Batterie niedrig",
                message=f"EcoFlow-Batterie liegt bei {int(round(soc))} %.",
                source="ecoflow",
                fingerprint=f"ecoflow_low_battery:{int(round(soc))}",
                recommended_action="EcoFlow-Batterie pruefen.",
            )
        )

    def evaluate_home_assistant_critical(self, rule: dict[str, Any]) -> dict[str, Any] | None:
        result = self._execute_green("home_assistant_get_problems")
        problems = result.get("result", {})
        critical = [
            item for item in problems.get("critical", []) if not item.get("ignored")
        ]
        if not critical:
            return None
        entity_id = str(critical[0].get("entity_id", "unknown"))
        return self.add_alert(
            _alert(
                rule,
                title="Home Assistant kritisch",
                message=f"Home Assistant meldet kritisch: {entity_id}.",
                source="home_assistant",
                fingerprint=f"ha_critical:{entity_id}",
                recommended_action="Home-Assistant-Problem pruefen.",
            )
        )

    def evaluate_gmail_security_email(self, rule: dict[str, Any]) -> dict[str, Any] | None:
        result = self._execute_green("gmail_unread_recent")
        email_result = result.get("result", {})
        for email in _collect_emails(email_result):
            classification = PriorityEngine().classify_email(email)
            if classification["priority"] == "high" and classification["category"] == "account_security":
                sender = str(email.get("sender") or "Unbekannter Absender")
                subject = str(email.get("subject") or "(kein Betreff)")
                return self.add_alert(
                    _alert(
                        rule,
                        title="Sicherheitsrelevante E-Mail",
                        message=f"{sender}: {subject}",
                        source="gmail",
                        fingerprint=f"gmail_security:{sender}:{subject}",
                        recommended_action=classification["recommended_action"],
                    )
                )
        return None

    def evaluate_timetree_today_events(self, rule: dict[str, Any]) -> dict[str, Any] | None:
        result = self._execute_green("timetree_today")
        calendar = result.get("result", {})
        events = calendar.get("events", [])
        count = calendar.get("count")
        if count is None:
            count = len(events) if isinstance(events, list) else 0
        if not count:
            return None
        return self.add_alert(
            _alert(
                rule,
                title="TimeTree-Termine heute",
                message=f"Heute gibt es {count} TimeTree-Termine.",
                source="timetree",
                fingerprint=f"timetree_today:{count}",
                recommended_action="Familienkalender pruefen.",
            )
        )

    def add_alert(self, alert: dict[str, Any]) -> dict[str, Any]:
        rule = _rule_for_alert(alert, self.load_rules()["rules"])
        cooldown = int(rule.get("cooldown_minutes", 0)) if rule else 0
        if self.apply_cooldown(alert["rule_id"], alert["fingerprint"], cooldown):
            return {
                "status": "suppressed_by_cooldown",
                "rule_id": alert["rule_id"],
                "fingerprint": alert["fingerprint"],
            }
        alerts = self._load_alerts()
        alerts.append(alert)
        self._save_alerts(alerts)
        return {"status": "created", "alert": alert}

    def list_alerts(self, limit: int = 50) -> list[dict[str, Any]]:
        alerts = [alert for alert in self._load_alerts() if not alert.get("acknowledged")]
        return alerts[-limit:]

    def clear_alerts(self) -> dict[str, bool]:
        self._save_alerts([])
        return {"cleared": True}

    def acknowledge_alert(self, alert_id: str) -> dict[str, Any]:
        alerts = self._load_alerts()
        for alert in alerts:
            if alert.get("id") == alert_id:
                alert["acknowledged"] = True
                self._save_alerts(alerts)
                return alert
        raise ValueError("Alert nicht gefunden.")

    def apply_cooldown(self, rule_id: str, fingerprint: str, cooldown_minutes: int) -> bool:
        if cooldown_minutes <= 0:
            return False
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=cooldown_minutes)
        for alert in self._load_alerts():
            if alert.get("rule_id") != rule_id or alert.get("fingerprint") != fingerprint:
                continue
            created_at = _parse_datetime(alert.get("created_at"))
            if created_at and created_at >= cutoff:
                return True
        return False

    def status(self) -> dict[str, Any]:
        rules = self.load_rules()["rules"]
        return {
            "enabled": os.getenv("WATCHER_ENABLED", "false").strip().lower() == "true",
            "interval_seconds": int(os.getenv("WATCHER_INTERVAL_SECONDS", "300")),
            "rules_count": len(rules),
            "active_alerts": len(self.list_alerts()),
            "last_run": self.last_run,
        }

    def _evaluate_rule(self, rule: dict[str, Any]) -> dict[str, Any] | None:
        rule_type = rule.get("type")
        if rule_type == "ecoflow_low_battery":
            return self.evaluate_ecoflow_low_battery(rule)
        if rule_type == "home_assistant_critical":
            return self.evaluate_home_assistant_critical(rule)
        if rule_type == "gmail_security_email":
            return self.evaluate_gmail_security_email(rule)
        if rule_type == "timetree_today_events":
            return self.evaluate_timetree_today_events(rule)
        return None

    def _execute_green(self, tool_name: str) -> dict[str, Any]:
        tool = self.registry.get(tool_name)
        if tool.risk != ActionRisk.GREEN:
            return {"tool": tool_name, "blocked": True, "risk": tool.risk}
        return self.registry.execute_tool(tool_name, {}, confirm=False)

    def _load_alerts(self) -> list[dict[str, Any]]:
        try:
            with self.alerts_file.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]

    def _save_alerts(self, alerts: list[dict[str, Any]]) -> None:
        self.alerts_file.parent.mkdir(parents=True, exist_ok=True)
        with self.alerts_file.open("w", encoding="utf-8") as file:
            json.dump(alerts, file, ensure_ascii=False, indent=2)
            file.write("\n")


def _alert(
    rule: dict[str, Any],
    title: str,
    message: str,
    source: str,
    fingerprint: str,
    recommended_action: str,
) -> dict[str, Any]:
    return {
        "id": uuid4().hex,
        "rule_id": rule["id"],
        "severity": rule.get("severity", "info"),
        "title": title,
        "message": message,
        "created_at": _now_iso(),
        "source": source,
        "fingerprint": fingerprint,
        "acknowledged": False,
        "recommended_action": recommended_action,
    }


def _rule_for_alert(alert: dict[str, Any], rules: list[dict[str, Any]]) -> dict[str, Any] | None:
    for rule in rules:
        if rule.get("id") == alert.get("rule_id"):
            return rule
    return None


def _collect_emails(result: dict[str, Any]) -> list[dict[str, Any]]:
    emails: list[dict[str, Any]] = []
    for provider in result.get("providers", []):
        if isinstance(provider, dict) and provider.get("connected") is True:
            emails.extend(email for email in provider.get("emails", []) if isinstance(email, dict))
    return emails


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_datetime(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
