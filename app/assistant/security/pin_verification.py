import hashlib
import os

from app.config.home_assistant_control_policy import load_home_assistant_control_policy


def is_pin_configured() -> bool:
    return bool(_pin_hash())


def verify_pin(pin: str) -> bool:
    """Verify a PIN against a configured hash without logging or storing the plain PIN."""
    configured = _pin_hash()
    if not configured:
        return False
    digest = hashlib.sha256(str(pin).encode("utf-8")).hexdigest()
    return digest == configured


def _pin_hash() -> str:
    env_hash = os.getenv("HA_CONTROL_CONFIRMATION_PIN_HASH", "").strip()
    if env_hash:
        return env_hash
    return str(load_home_assistant_control_policy().get("confirmation_pin_hash", "")).strip()
