"""Optional Firebase Auth integration.

Enabled when a service account is configured via either:
  - FIREBASE_SERVICE_ACCOUNT=/path/to/serviceAccount.json   (recommended)
  - GOOGLE_APPLICATION_CREDENTIALS (standard Google env var)

If firebase-admin is not installed or no credentials are found, the app
silently falls back to the built-in local JWT auth — nothing breaks.
"""
import logging
import os
from typing import Optional

log = logging.getLogger(__name__)

try:
    import firebase_admin
    from firebase_admin import auth as firebase_auth_mod
    from firebase_admin import credentials
except ImportError:  # firebase-admin not installed -> feature disabled
    firebase_admin = None
    firebase_auth_mod = None
    credentials = None

_state = {"checked": False, "enabled": False}


def firebase_enabled() -> bool:
    if _state["checked"]:
        return _state["enabled"]
    _state["checked"] = True

    if firebase_admin is None:
        log.info("firebase-admin not installed; Firebase auth disabled.")
        return False

    sa_path = os.getenv("FIREBASE_SERVICE_ACCOUNT")
    try:
        if sa_path and os.path.exists(sa_path):
            cred = credentials.Certificate(sa_path)
        elif os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
            cred = credentials.ApplicationDefault()
        else:
            log.info("No Firebase credentials configured; Firebase auth disabled.")
            return False
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        _state["enabled"] = True
        log.info("Firebase Auth enabled.")
    except Exception as exc:  # bad JSON, wrong project, network, etc.
        log.warning("Firebase init failed (%s); falling back to local JWT.", exc)
    return _state["enabled"]


def verify_firebase_token(token: str) -> Optional[dict]:
    """Verify a Firebase ID token. Returns decoded claims, or None if the
    token is invalid OR Firebase is disabled (so caller can fall back)."""
    if not firebase_enabled():
        return None
    try:
        return firebase_auth_mod.verify_id_token(token, check_revoked=False)
    except Exception as exc:
        log.debug("Firebase token verification failed: %s", exc)
        return None


def reset_for_tests():
    _state.update(checked=False, enabled=False)
