from typing import Any

from app.assistant.formatters.ecoflow_formatter import format_ecoflow_energy_answer
from app.assistant.priority_engine import PriorityEngine
from app.tools.productivity.email_service import clean_email_snippet


def format_daily_briefing(results: dict[str, Any]) -> str:
    engine = PriorityEngine()
    priorities = engine.build_daily_priorities(results)
    lines = ["Tagesstatus"]
    alert_lines = _watcher_alert_lines(results.get("watcher_alerts", {}))
    if alert_lines:
        lines.append("")
        lines.extend(alert_lines)
    lines.extend(["", "Wichtig zuerst:"])
    if priorities:
        for index, item in enumerate(priorities[:5], start=1):
            lines.append(f"{index}. {_priority_sentence(item)}")
    else:
        lines.append("1. Keine wirklich wichtigen neuen E-Mails erkannt.")

    lines.append("")
    lines.extend(_email_lines(results.get("gmail_unread_recent", {}), "Posteingang:", include_priority=True))
    low_priority_lines = _low_priority_email_lines(results.get("gmail_unread_recent", {}))
    if low_priority_lines:
        lines.append("")
        lines.extend(low_priority_lines)
    lines.append("")
    lines.extend(_timetree_lines(results.get("timetree_today", {}), "Kalender / TimeTree:"))
    lines.append("")
    lines.extend(_home_assistant_lines(results.get("home_assistant_get_problems", {}), "Haus / Home Assistant:"))
    lines.append("")
    lines.append("Energie / EcoFlow:")
    lines.extend(format_ecoflow_energy_answer(results.get("ecoflow_energy_overview", {})).splitlines())
    lines.append("")
    lines.append("Empfohlene naechste Schritte:")
    for step in _recommended_steps(priorities, results):
        lines.append(f"- {step}")
    return _join_lines(lines)


def format_home_check(results: dict[str, Any]) -> str:
    lines = ["Hauscheck", ""]
    lines.extend(_home_assistant_lines(results.get("home_assistant_get_problems", {}), "Home Assistant"))
    lines.append("")
    lines.append("EcoFlow")
    lines.extend(format_ecoflow_energy_answer(results.get("ecoflow_energy_overview", {})).splitlines())
    lines.append("")
    lines.append("Vorschlag: Kritische und Warn-Entities pruefen. Ich schalte nichts automatisch.")
    return _join_lines(lines)


def format_inbox_briefing(results: dict[str, Any]) -> str:
    return _join_lines(_email_lines(results.get("gmail_unread_recent", {}), "Posteingang"))


def format_family_calendar_briefing(results: dict[str, Any]) -> str:
    return _join_lines(_timetree_lines(results.get("timetree_today", {}), "Familienkalender"))


def _email_lines(result: dict[str, Any], heading: str, include_priority: bool = False) -> list[str]:
    if not isinstance(result, dict):
        return [heading, "- Keine E-Mail-Daten verfuegbar."]
    if _has_gmail_error(result):
        message = str(result.get("message") or "Gmail ist noch nicht korrekt verbunden.").strip()
        return [heading, f"- {message}"]

    count = result.get("unread_count")
    if count is None:
        count = result.get("total_email_count", 0)
    lines = [heading, f"- Ich habe {count} Gmail-Nachrichten gefunden."]
    emails = _collect_emails(result)
    if not emails:
        return lines

    engine = PriorityEngine()
    if include_priority:
        emails = sorted(
            emails,
            key=lambda item: _email_priority_rank(engine.classify_email(item)["priority"]),
        )

    if include_priority:
        emails = [
            email
            for email in emails
            if engine.classify_email(email)["priority"] in {"critical", "high", "medium"}
        ]

    for index, email in enumerate(emails[:5], start=1):
        sender = str(email.get("sender") or "Unbekannter Absender").strip()
        subject = clean_email_snippet(str(email.get("subject") or "(kein Betreff)"))
        if include_priority:
            classification = engine.classify_email(email)
            lines.append(
                (
                    f"- {_priority_label(classification['priority'])}: "
                    f"{sender}: {subject} "
                    f"({classification['category']}; {classification['reason']})"
                )
            )
        else:
            lines.append(f"{index}. {sender}: {subject}")
    return lines


def _low_priority_email_lines(result: dict[str, Any]) -> list[str]:
    if not isinstance(result, dict) or _has_gmail_error(result):
        return []
    engine = PriorityEngine()
    low_items: list[str] = []
    for email in _collect_emails(result):
        classification = engine.classify_email(email)
        if classification["priority"] not in {"low", "info"}:
            continue
        sender = str(email.get("sender") or "Unbekannter Absender").strip()
        subject = clean_email_snippet(str(email.get("subject") or "(kein Betreff)"))
        low_items.append(f"- {sender}: {classification['category']} - {subject}")
        if len(low_items) >= 3:
            break
    if not low_items:
        return []
    return ["Info / Niedrige Prioritaet:", *low_items]


def _collect_emails(result: dict[str, Any]) -> list[dict[str, Any]]:
    emails: list[dict[str, Any]] = []
    for provider in result.get("providers", []):
        if isinstance(provider, dict) and provider.get("connected") is True:
            emails.extend(email for email in provider.get("emails", []) if isinstance(email, dict))
    return emails


def _has_gmail_error(result: dict[str, Any]) -> bool:
    return any(
        provider.get("provider") == "gmail" and provider.get("error") is True
        for provider in result.get("providers", [])
        if isinstance(provider, dict)
    )


def _timetree_lines(result: dict[str, Any], heading: str) -> list[str]:
    if not isinstance(result, dict):
        return [heading, "- Keine TimeTree-Daten verfuegbar."]
    if result.get("enabled") is False:
        return [heading, "- TimeTree ist vorbereitet, aber der ICS-Import ist deaktiviert."]
    if result.get("connected") is False:
        return [heading, f"- {result.get('message', 'TimeTree ICS-Datei wurde nicht gefunden.')}"]
    events = result.get("events", [])
    if not events:
        return [heading, "- Heute stehen keine TimeTree-Termine an."]
    lines = [heading, f"- Heute stehen {len(events)} TimeTree-Termine an:"]
    for index, event in enumerate(events[:5], start=1):
        prefix = "Ganztagig" if event.get("all_day") else _event_time(event)
        lines.append(f"{index}. {prefix} {event.get('title', '')}".strip())
    return lines


def _home_assistant_lines(result: dict[str, Any], heading: str) -> list[str]:
    if not isinstance(result, dict):
        return [heading, "- Keine Home-Assistant-Daten verfuegbar."]
    critical_count = result.get("critical_count", 0)
    warning_count = result.get("warning_count", 0)
    lines = [heading]
    if critical_count:
        lines.append(
            f"- Kritisch: {critical_count}, Warnungen: {warning_count}, Infos: {result.get('informational_count', 0)}"
        )
    else:
        lines.append("- Keine echten kritischen Home-Assistant-Probleme.")
        lines.append(f"- {warning_count} Warnungen.")

    for entity in (result.get("critical", []) + result.get("warning", []))[:5]:
        lines.append(f"- {entity.get('entity_id', 'unknown')}: {entity.get('state', '')}".strip())
    for entity in result.get("informational", [])[:3]:
        if entity.get("ignored"):
            lines.append(f"- {entity.get('message', 'Bekannte optionale Entity ignoriert.')}")
    return lines


def _event_time(event: dict[str, Any]) -> str:
    start = str(event.get("start", ""))
    return start[11:16] if "T" in start else "Ganztagig"


def _priority_sentence(item: dict[str, Any]) -> str:
    if item.get("type") == "ecoflow" and item.get("reason") == "EcoFlow-Batterie unter Schwellwert.":
        source = item.get("source_result", {})
        soc = source.get("soc_percent") if isinstance(source, dict) else None
        if soc is not None:
            return f"EcoFlow-Batterie ist niedrig: {int(round(float(soc)))} %. {item.get('recommended_action')}"
    if item.get("type") == "email":
        return f"{item.get('title', 'E-Mail')}. {item.get('recommended_action')}"
    return f"{item.get('title', 'Prioritaet')}. {item.get('recommended_action')}"


def _watcher_alert_lines(result: dict[str, Any]) -> list[str]:
    alerts = result.get("alerts", []) if isinstance(result, dict) else []
    if not alerts:
        return []
    lines = ["Proaktive Hinweise:"]
    for alert in alerts[:5]:
        lines.append(f"- {alert.get('title')}: {alert.get('message')}")
    return lines


def _recommended_steps(priorities: list[dict[str, Any]], results: dict[str, Any]) -> list[str]:
    steps = [_specific_next_step(item) for item in priorities[:5] if item.get("recommended_action")]
    ha = results.get("home_assistant_get_problems", {})
    if isinstance(ha, dict) and ha.get("warning_count", 0):
        if _has_backup_warning(ha):
            steps.append("Home-Assistant-Backup-Konfiguration pruefen.")
        else:
            steps.append("Home-Assistant-Warnungen pruefen.")
    ecoflow = results.get("ecoflow_energy_overview", {})
    if _has_stale_ecoflow_values(ecoflow):
        steps.append("EcoFlow-Tageswerte bei Gelegenheit pruefen.")
    return steps or ["Keine direkte Aktion noetig."]


def _specific_next_step(item: dict[str, Any]) -> str:
    title = str(item.get("title", "")).lower()
    category = str(item.get("category", ""))
    reason = str(item.get("reason", "")).lower()
    if "github" in title and ("oauth" in title or "oauth" in reason):
        return "GitHub-OAuth-App pruefen."
    if "openai" in title and ("datenexport" in title or "data export" in title or "export" in title):
        return "OpenAI-Datenexport pruefen."
    if category == "account_security":
        return "Kontoaktion pruefen."
    if category == "academy" or "fernakademie" in title:
        return "Fernakademie-Nachricht oeffnen."
    if item.get("type") == "ecoflow" and "batterie" in reason:
        return "EcoFlow-Batterie pruefen."
    if item.get("type") == "ecoflow":
        return "EcoFlow-kritische Entity pruefen."
    return str(item.get("recommended_action"))


def _has_stale_ecoflow_values(ecoflow: Any) -> bool:
    if not isinstance(ecoflow, dict):
        return False
    return any(
        isinstance(warning, dict) and warning.get("code") == "stale_value"
        for warning in ecoflow.get("warnings", [])
    )


def _has_backup_warning(ha: dict[str, Any]) -> bool:
    for entity in ha.get("warning", []):
        text = f"{entity.get('entity_id', '')} {entity.get('friendly_name', '')} {entity.get('message', '')}".lower()
        if "backup" in text:
            return True
    return False


def _priority_label(priority: str) -> str:
    return {
        "critical": "Kritisch",
        "high": "Hoch",
        "medium": "Mittel",
        "low": "Niedrig",
        "info": "Info",
    }.get(priority, "Info")


def _email_priority_rank(priority: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}.get(priority, 9)


def _join_lines(lines: list[str]) -> str:
    return "\n".join(line for line in lines if line is not None).strip()
