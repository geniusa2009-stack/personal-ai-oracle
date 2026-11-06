"""Minimal fail-closed password gate for the single-owner Oracle web app."""

from __future__ import annotations

import hmac
import os
from typing import Any

AUTHENTICATED_SESSION_KEY = "oracle_authenticated"
MIN_PASSWORD_LENGTH = 16


def verify_app_password(candidate: str, expected: str | None = None) -> bool:
    """Compare an app password without timing-sensitive string equality."""
    configured = expected if expected is not None else os.environ.get("ORACLE_APP_PASSWORD", "")
    if not isinstance(candidate, str) or not isinstance(configured, str):
        return False
    if len(configured) < MIN_PASSWORD_LENGTH:
        return False
    return hmac.compare_digest(candidate.encode("utf-8"), configured.encode("utf-8"))


def require_app_auth(st_module: Any) -> None:
    """Stop rendering the application until the owner authenticates this session."""
    configured = os.environ.get("ORACLE_APP_PASSWORD", "")
    if len(configured) < MIN_PASSWORD_LENGTH:
        st_module.error(
            "التطبيق مقفول: اضبط ORACLE_APP_PASSWORD في متغيرات البيئة "
            f"بكلمة مرور لا تقل عن {MIN_PASSWORD_LENGTH} حرفاً."
        )
        st_module.stop()
        return

    if st_module.session_state.get(AUTHENTICATED_SESSION_KEY) is True:
        return

    st_module.title("🔐 Personal AI Oracle")
    st_module.caption("سجّل الدخول للوصول إلى بياناتك الشخصية.")
    with st_module.form("oracle_owner_login", clear_on_submit=True):
        candidate = st_module.text_input("كلمة مرور التطبيق", type="password")
        submitted = st_module.form_submit_button("دخول", use_container_width=True)

    if submitted:
        if verify_app_password(candidate, configured):
            st_module.session_state[AUTHENTICATED_SESSION_KEY] = True
            st_module.rerun()
        else:
            st_module.error("كلمة المرور غير صحيحة.")

    st_module.stop()
