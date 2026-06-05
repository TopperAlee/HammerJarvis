import os
from typing import Any

from app.config.entity_overrides import get_ignore_reason, is_ignored_entity
from app.config.personal_priority_rules import load_personal_priority_rules
from app.config.priority_rules import as_search_text, load_priority_rules


PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
CATEGORY_ORDER = {
    "account_security": 0,
    "security": 0,
    "academy": 1,
    "home_assistant": 2,
    "energy": 3,
    "job": 4,
    "unknown": 5,
}
TRUSTED_SECURITY_SENDERS = (
    "github.com",
    "github",
    "openai.com",
    "openai",
    "google.com",
    "microsoft.com",
    "paypal.com",
)
SECURITY_SUBJECT_TERMS = (
    "oauth application",
    "datenexport",
    "data export",
    "password changed",
    "passwort geaendert",
    "login attempt",
    "neuer login",
    "suspicious",
    "verdaechtig",
    "2fa",
    "recovery",
    "wiederherstellung",
    "security alert",
    "sicherheitswarnung",
)
STRONG_SECURITY_PHRASES = (
    "a third-party oauth application has been added",
    "dein datenexport wurde gestartet",
    "your data export has started",
    "password was changed",
    "new sign-in",
    "security alert",
)
MARKETING_INDICATORS = (
    "newsletter",
    "news@",
    "noreply marketing",
    "angebot",
    "angebote",
    "sale",
    "rabatt",
    "deal",
    "deals",
    "jackpot",
    "gewinn",
    "gewinnen",
    "-80%",
    "%",
    "eur",
    "€",
    "all-in",
    "jetzt erhaeltlich",
    "jetzt erhältlich",
    "limited offer",
    "nur heute",
    "black friday",
    "camping",
    "urlaub",
    "reise",
    "roadtrip",
    "malediven",
    "tuerkei",
    "türkei",
    "voyage prive",
    "voyage privé",
    "lotto",
    "dreame",
    "conrad",
    "ea sports",
    "anycubic",
)


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
        subject_text = as_search_text(subject, snippet)

        if "github" in text and "oauth application" in text:
            return _classification(
                "high",
                "account_security",
                "GitHub meldet eine OAuth-App.",
                "Pruefen, ob du diese OAuth-App selbst autorisiert hast.",
                source="security_rule",
                confidence="high",
            )

        if _is_strong_security(sender, subject_text):
            return _classification(
                "high",
                "account_security",
                "Konto- oder Sicherheitsaktion erkannt.",
                _security_recommended_action(subject_text),
                source="security_rule",
                confidence="high",
            )

        personal_classification = self._classify_with_personal_rules(
            sender,
            subject,
            text,
        )
        if personal_classification:
            return personal_classification

        if _contains_any(text, self.rules["email_suspicious_keywords"]):
            return _classification(
                "low",
                "spam",
                "Verdaechtige Finanz- oder Aktienwerbung.",
                "Nicht anklicken; bei Bedarf loeschen, aber nicht automatisch.",
                source="marketing_rule",
                confidence="high",
            )

        if _contains_marketing(text):
            return _classification(
                "low",
                "marketing",
                "Marketing- oder Produktwerbung.",
                "Bei Interesse spaeter ansehen.",
                source="marketing_rule",
                confidence="high",
            )

        if "fernakademie" in text or "online-plattform" in text:
            return _classification(
                "high",
                "academy",
                "Nachricht aus der Lernplattform.",
                "Fernakademie-Nachricht oeffnen.",
                source="generic_rule",
                confidence="high",
            )
        if "ollama" in text and "thank you for joining" in text:
            return _classification(
                "info",
                "info",
                "Willkommens- oder Infomail.",
                "Keine direkte Aktion noetig.",
                source="generic_rule",
                confidence="high",
            )
        if "linkedin" in text and ("job" in text or "stellen" in text):
            return _classification(
                "medium",
                "job",
                "LinkedIn Jobbenachrichtigung.",
                "Bei Interesse spaeter pruefen.",
                source="generic_rule",
                confidence="medium",
            )
        if (
            "campact" in text
            or _sender_contains(sender, self.rules["email_low_senders"])
            or "newsletter" in text
        ):
            return _classification(
                "low",
                "newsletter",
                "Newsletter oder Kampagnenmail.",
                "Bei Interesse spaeter ansehen.",
                source="marketing_rule",
                confidence="high",
            )
        if _contains_any(text, self.rules["email_high_keywords"]):
            return _classification(
                "high",
                _category_for_high_text(text),
                "Enthaelt wichtige Stichwoerter.",
                "Zeitnah pruefen.",
                source="generic_rule",
                confidence="medium",
            )
        if _contains_any(text, self.rules["email_medium_keywords"]):
            return _classification(
                "medium",
                "info",
                "Normale Benachrichtigung oder Erinnerung.",
                "Bei Gelegenheit pruefen.",
                source="generic_rule",
                confidence="medium",
            )
        if _looks_automated(sender):
            return _classification(
                "info",
                "unknown",
                "Automatisierter Absender ohne hohe Prioritaet.",
                "Keine direkte Aktion noetig.",
                source="generic_rule",
                confidence="medium",
            )
        if _looks_personal(sender):
            return _classification(
                "medium",
                "unknown",
                "Persoenlich wirkender Absender, aber keine hohe Prioritaet erkannt.",
                "Bei Gelegenheit pruefen.",
                source="generic_rule",
                confidence="low",
            )
        return _classification(
            "info",
            "unknown",
            "Keine hohe Prioritaet erkannt.",
            "Keine direkte Aktion noetig.",
            source="generic_rule",
            confidence="low",
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
                    _recommended_action_for_rule(rule, sender=sender, subject=subject),
                    source="personal_rule",
                    confidence="high",
                )
        for rule in self.personal_rules.get("subject_rules", []):
            match = str(rule.get("match", "")).lower()
            if match and match in subject_lower:
                return _classification(
                    str(rule.get("priority", "info")),
                    str(rule.get("category", "unknown")),
                    str(rule.get("reason", "Persoenliche Prioritaetsregel.")),
                    _recommended_action_for_rule(rule, sender=sender, subject=subject),
                    source="personal_rule",
                    confidence="high",
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
                "confidence": "high",
                "source": "personal_rule",
            }
        state = str(problem.get("state") or "").lower()
        priority = "critical" if state == "unavailable" else "medium"
        return {
            "priority": priority,
            "category": "home_assistant",
            "reason": f"Home-Assistant-Entity ist {state or 'problematisch'}.",
            "recommended_action": "Entity in Home Assistant pruefen.",
            "confidence": "medium",
            "source": "generic_rule",
        }

    def build_daily_priorities(self, results: dict[str, Any]) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for email in _collect_emails(results.get("gmail_unread_recent", {})):
            classification = self.classify_email(email)
            if classification["priority"] in {"critical", "high", "medium"}:
                candidates.append(
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
                    candidates.append(
                        {
                            **classification,
                            "type": "home_assistant",
                            "title": (
                                f"{problem.get('entity_id', 'unknown')}: "
                                f"{problem.get('state', '')}"
                            ),
                            "source": problem,
                        }
                    )

        ecoflow_priority = _ecoflow_priority(results.get("ecoflow_energy_overview", {}))
        if ecoflow_priority:
            candidates.append(ecoflow_priority)

        allowed_high_categories = {
            "account_security",
            "academy",
            "home_assistant",
            "energy",
        }
        filtered = [
            item
            for item in candidates
            if item["priority"] in {"critical", "high"}
            and item["category"] in allowed_high_categories
        ]
        if not filtered:
            filtered = [
                item
                for item in candidates
                if item["priority"] == "medium"
                and item["category"] in {"job", "energy"}
            ]
        return sorted(
            filtered,
            key=lambda item: (
                PRIORITY_ORDER.get(item["priority"], 9),
                CATEGORY_ORDER.get(item["category"], 9),
            ),
        )


def _classification(
    priority: str,
    category: str,
    reason: str,
    recommended_action: str,
    source: str = "generic_rule",
    confidence: str = "medium",
) -> dict[str, str]:
    return {
        "priority": priority,
        "category": category,
        "reason": reason,
        "recommended_action": recommended_action,
        "confidence": confidence,
        "source": source,
    }


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _is_strong_security(sender: str, subject_text: str) -> bool:
    sender_text = sender.lower()
    trusted = any(value in sender_text for value in TRUSTED_SECURITY_SENDERS)
    security_subject = any(term in subject_text for term in SECURITY_SUBJECT_TERMS)
    strong_phrase = any(phrase in subject_text for phrase in STRONG_SECURITY_PHRASES)
    return strong_phrase or (trusted and security_subject)


def _security_recommended_action(subject_text: str) -> str:
    if "oauth" in subject_text:
        return "Pruefen, ob du diese OAuth-App selbst autorisiert hast."
    if "datenexport" in subject_text or "data export" in subject_text or "export" in subject_text:
        return "Pruefen, ob du den Datenexport selbst gestartet hast."
    return "Pruefen, ob du diese Kontoaktion selbst ausgeloest hast."


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
    automated_markers = (
        "newsletter",
        "noreply",
        "no-reply",
        "notification",
        "benachrichtigung",
        "news@",
        "info@",
        "marketing@",
        "hello@",
    )
    return bool(sender.strip()) and not any(marker in sender_lower for marker in automated_markers)


def _looks_automated(sender: str) -> bool:
    sender_lower = sender.lower()
    automated_markers = (
        "newsletter",
        "noreply",
        "no-reply",
        "notification",
        "benachrichtigung",
        "news@",
        "info@",
        "marketing@",
        "hello@",
    )
    return any(marker in sender_lower for marker in automated_markers)


def _contains_marketing(text: str) -> bool:
    return any(marker in text for marker in MARKETING_INDICATORS)


def _recommended_action_for_rule(
    rule: dict[str, Any],
    sender: str = "",
    subject: str = "",
) -> str:
    priority = str(rule.get("priority", "info"))
    category = str(rule.get("category", "unknown"))
    text = as_search_text(sender, subject, rule.get("match", ""))
    if category == "account_security":
        if "datenexport" in text or "data export" in text or "export" in text:
            return "Pruefen, ob du den Datenexport selbst gestartet hast."
        return "Pruefen, ob du diese Kontoaktion selbst ausgeloest hast."
    if category in {"security", "account_security"} and "github" in text:
        return "Pruefen, ob du diese OAuth-App selbst autorisiert hast."
    if category == "academy":
        return "Fernakademie-Nachricht oeffnen."
    if priority in {"high", "critical"}:
        return "Zeitnah pruefen."
    if priority == "medium":
        return "Bei Gelegenheit pruefen."
    if category in {"marketing", "newsletter", "info"}:
        return "Bei Interesse spaeter ansehen."
    return "Keine Aktion noetig."


def _ecoflow_priority(ecoflow: Any) -> dict[str, Any] | None:
    if not isinstance(ecoflow, dict):
        return None

    human_status = ecoflow.get("human_status", {})
    overall = human_status.get("overall") if isinstance(human_status, dict) else None
    headline = (
        str(human_status.get("headline") or "EcoFlow-Warnung")
        if isinstance(human_status, dict)
        else "EcoFlow-Warnung"
    )
    critical_count = int(ecoflow.get("critical_count") or 0)
    soc = _to_float(ecoflow.get("soc_percent"))
    threshold = _low_battery_threshold()

    if soc is not None and soc <= threshold:
        return {
            "priority": "high",
            "category": "energy",
            "reason": "EcoFlow-Batterie unter Schwellwert.",
            "recommended_action": "EcoFlow-Batterie pruefen.",
            "confidence": "high",
            "source": "generic_rule",
            "type": "ecoflow",
            "title": headline,
            "source_result": ecoflow,
        }

    if overall == "critical" or critical_count > 0:
        return {
            "priority": "high",
            "category": "energy",
            "reason": "EcoFlow meldet ein kritisches Problem.",
            "recommended_action": "EcoFlow-kritische Entity pruefen.",
            "confidence": "high",
            "source": "generic_rule",
            "type": "ecoflow",
            "title": headline,
            "source_result": ecoflow,
        }
    return None


def _low_battery_threshold() -> float:
    try:
        return float(os.getenv("ECOFLOW_LOW_BATTERY_THRESHOLD_PERCENT", "20"))
    except ValueError:
        return 20.0


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
