from typing import Any

from app.config.entity_overrides import get_ignore_reason, is_ignored_entity
from app.config.personal_priority_rules import load_personal_priority_rules
from app.config.priority_rules import as_search_text, load_priority_rules


PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


class PriorityEngine:
    def __init__(self, rules: dict[str, list[str]] | None = None) -> None:
        self.rules = rules or load_priority_rules()
        self.personal_rules = load_personal_priority_rules()

    def score_email(self, email: dict[str, Any]) -> dict[str, Any]:
        return self.classify_email(email)

    def classify_email(self, email: dict[str, Any]) -> dict[str, Any]:
        sender = str(email.get("sender") or "")
        subject = str(email.get("subject") or "")
        snippet = str(email.get("snippet") or "")
        text = as_search_text(sender, subject, snippet)

        if "github" in text and "oauth application" in text:
            return _classification(
                "high",
                "security",
                "GitHub meldet eine OAuth-App.",
                "Pruefen, ob du diese OAuth-App selbst autorisiert hast.",
                source="hard_rule",
            )

        personal_classification = self._classify_with_personal_rules(sender, subject, text)
        if personal_classification:
            return personal_classification

        if "fernakademie" in text or "online-plattform" in text:
            return _classification(
                "high",
                "academy",
                "Nachricht aus der Lernplattform.",
                "Fernakademie-Nachricht pruefen.",
                source="heuristic",
            )
        if "ollama" in text and "thank you for joining" in text:
            return _classification(
                "info",
                "info",
                "Willkommens- oder Infomail.",
                "Keine direkte Aktion noetig.",
                source="heuristic",
            )
        if _contains_any(text, self.rules["email_suspicious_keywords"]):
            return _classification(
                "low",
                "spam",
                "Verdaechtige Finanz- oder Aktienwerbung.",
                "Nicht anklicken; bei Bedarf loeschen, aber nicht automatisch.",
                source="heuristic",
            )
        if "linkedin" in text and ("job" in text or "stellen" in text):
            return _classification(
                "medium",
                "job",
                "LinkedIn Jobbenachrichtigung.",
                "Bei Interesse spaeter pruefen.",
                source="heuristic",
            )
        if "campact" in text or _sender_contains(sender, self.rules["email_low_senders"]) or "newsletter" in text:
            return _classification(
                "low",
                "newsletter",
                "Newsletter oder Kampagnenmail.",
                "Kann spaeter gelesen werden.",
                source="heuristic",
            )
        if _contains_marketing(text):
            return _classification(
                "low",
                "marketing",
                "Marketing- oder Produktwerbung.",
                "Kann ignoriert oder spaeter gelesen werden.",
                source="heuristic",
            )
        if _contains_any(text, self.rules["email_high_keywords"]):
            return _classification(
                "high",
                _category_for_high_text(text),
                "Enthaelt wichtige Stichwoerter.",
                "Zeitnah pruefen.",
                source="heuristic",
            )
        if _contains_any(text, self.rules["email_medium_keywords"]):
            return _classification(
                "medium",
                "info",
                "Normale Benachrichtigung oder Erinnerung.",
                "Bei Gelegenheit pruefen.",
                source="heuristic",
            )
        if _looks_automated(sender):
            return _classification(
                "info",
                "unknown",
                "Automatisierter Absender ohne hohe Prioritaet.",
                "Keine direkte Aktion noetig.",
                source="heuristic",
            )
        if _looks_personal(sender):
            return _classification(
                "medium",
                "unknown",
                "Persoenlich wirkender Absender, aber keine hohe Prioritaet erkannt.",
                "Kurz pruefen.",
                source="heuristic",
            )
        return _classification(
            "info",
            "unknown",
            "Keine hohe Prioritaet erkannt.",
            "Keine direkte Aktion noetig.",
            source="heuristic",
        )

    def _classify_with_personal_rules(
        self,
        sender: str,
        subject: str,
        text: str,
    ) -> dict[str, str] | None:
        sender_lower = sender.lower()
        subject_lower = subject.lower()
        for rule in self.personal_rules.get("sender_rules", []):
            match = str(rule.get("match", "")).lower()
            if match and (match in sender_lower or match in text):
                return _classification(
                    str(rule.get("priority", "info")),
                    str(rule.get("category", "unknown")),
                    str(rule.get("reason", "Persoenliche Prioritaetsregel.")),
                    _recommended_action_for_rule(rule),
                    source="personal_rule",
                )
        for rule in self.personal_rules.get("subject_rules", []):
            match = str(rule.get("match", "")).lower()
            if match and match in subject_lower:
                return _classification(
                    str(rule.get("priority", "info")),
                    str(rule.get("category", "unknown")),
                    str(rule.get("reason", "Persoenliche Prioritaetsregel.")),
                    _recommended_action_for_rule(rule),
                    source="personal_rule",
                )
        return None

    def score_home_assistant_problem(self, problem: dict[str, Any]) -> dict[str, Any]:
        entity_id = str(problem.get("entity_id") or "")
        if is_ignored_entity(entity_id):
            return {
                "priority": "info",
                "category": "ignored_entity",
                "reason": get_ignore_reason(entity_id) or "Bekannte optionale Entity.",
                "recommended_action": "Keine direkte Aktion noetig.",
            }
        state = str(problem.get("state") or "").lower()
        priority = "critical" if state == "unavailable" else "medium"
        return {
            "priority": priority,
            "category": "home_assistant",
            "reason": f"Home-Assistant-Entity ist {state or 'problematisch'}.",
            "recommended_action": "Entity in Home Assistant pruefen.",
        }

    def build_daily_priorities(self, results: dict[str, Any]) -> list[dict[str, Any]]:
        priorities: list[dict[str, Any]] = []
        for email in _collect_emails(results.get("gmail_unread_recent", {})):
            classification = self.classify_email(email)
            if classification["priority"] in {"high", "critical"}:
                priorities.append(
                    {
                        **classification,
                        "type": "email",
                        "title": _email_title(email),
                        "source": email,
                    }
                )

        ha = results.get("home_assistant_get_problems", {})
        if isinstance(ha, dict):
            for problem in ha.get("critical", []):
                classification = self.score_home_assistant_problem(problem)
                if classification["priority"] == "critical":
                    priorities.append(
                        {
                            **classification,
                            "type": "home_assistant",
                            "title": f"{problem.get('entity_id', 'unknown')}: {problem.get('state', '')}",
                            "source": problem,
                        }
                    )

        ecoflow = results.get("ecoflow_energy_overview", {})
        if isinstance(ecoflow, dict):
            headline = str(ecoflow.get("human_status", {}).get("headline") or "")
            severity = "high" if ecoflow.get("critical_count", 0) else "medium"
            if ecoflow.get("warning_count_by_severity", 0) or ecoflow.get("critical_count", 0):
                priorities.append(
                    {
                        "priority": severity,
                        "category": "energy",
                        "reason": "EcoFlow meldet Warnungen.",
                        "recommended_action": "EcoFlow-Warnungen pruefen.",
                        "type": "ecoflow",
                        "title": headline or "EcoFlow-Warnung",
                        "source": ecoflow,
                    }
                )

        return sorted(priorities, key=lambda item: PRIORITY_ORDER.get(item["priority"], 9))


def _classification(
    priority: str,
    category: str,
    reason: str,
    recommended_action: str,
    source: str = "heuristic",
) -> dict[str, str]:
    return {
        "priority": priority,
        "category": category,
        "reason": reason,
        "recommended_action": recommended_action,
        "source": source,
    }


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _sender_contains(sender: str, values: list[str]) -> bool:
    sender_lower = sender.lower()
    return any(value in sender_lower for value in values)


def _category_for_high_text(text: str) -> str:
    if "rechnung" in text or "payment" in text or "bank" in text:
        return "payment"
    if "security" in text or "sicherheit" in text or "oauth" in text or "login" in text:
        return "security"
    if "fernakademie" in text or "online-plattform" in text:
        return "academy"
    return "unknown"


def _looks_personal(sender: str) -> bool:
    sender_lower = sender.lower()
    automated_markers = ("newsletter", "noreply", "no-reply", "notification", "benachrichtigung")
    return bool(sender.strip()) and not any(marker in sender_lower for marker in automated_markers)


def _looks_automated(sender: str) -> bool:
    sender_lower = sender.lower()
    automated_markers = ("newsletter", "noreply", "no-reply", "notification", "benachrichtigung")
    return any(marker in sender_lower for marker in automated_markers)


def _contains_marketing(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "jackpot",
            "jetzt erhaeltlich",
            "jetzt erhältlich",
            "angebot",
            "rabatt",
            "sale",
            "produktwerbung",
            "werbung",
            "promotion",
        )
    )


def _recommended_action_for_rule(rule: dict[str, Any]) -> str:
    priority = str(rule.get("priority", "info"))
    category = str(rule.get("category", "unknown"))
    if priority in {"high", "critical"}:
        return "Zeitnah pruefen."
    if priority == "medium":
        return "Bei Gelegenheit pruefen."
    if category in {"marketing", "newsletter"}:
        return "Kann ignoriert oder spaeter gelesen werden."
    return "Keine direkte Aktion noetig."


def _collect_emails(result: dict[str, Any]) -> list[dict[str, Any]]:
    emails: list[dict[str, Any]] = []
    if not isinstance(result, dict):
        return emails
    for provider in result.get("providers", []):
        if isinstance(provider, dict) and provider.get("connected") is True:
            emails.extend(email for email in provider.get("emails", []) if isinstance(email, dict))
    return emails


def _email_title(email: dict[str, Any]) -> str:
    sender = str(email.get("sender") or "Unbekannter Absender").strip()
    subject = str(email.get("subject") or "(kein Betreff)").strip()
    return f"{sender}: {subject}"
