"""Streamlit OIDC authentication plus explicit single-account authorization."""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from nexus.config import allowed_emails, is_auth_configured, is_dev_auth_bypass


@dataclass(frozen=True)
class Identity:
    owner_id: str
    email: str
    display_name: str
    is_development: bool = False


def require_identity() -> Identity | None:
    if is_dev_auth_bypass() and not is_auth_configured():
        email = "local@nexus.invalid"
        st.sidebar.warning("Local development authentication bypass is enabled.")
        return Identity("dev:local", email, "NEXUS User", True)

    if not is_auth_configured():
        st.title("NEXUS")
        st.error("Secure sign-in is not configured. Add an OIDC provider in Streamlit secrets, or enable the local-only development bypass.")
        st.code("NEXUS_DEV_AUTH_BYPASS=true  # local development only")
        st.stop()

    emails = allowed_emails()
    if not emails:
        st.title("NEXUS")
        st.error("Set `NEXUS_ALLOWED_EMAILS` or `[access].allowed_emails` to authorize the personal account.")
        st.stop()

    if not bool(getattr(st.user, "is_logged_in", False)):
        st.title("NEXUS")
        st.markdown("### Your personal command center")
        st.caption("Sign in through the configured identity provider to continue.")
        st.button("Continue with secure sign-in", on_click=st.login, type="primary")
        st.stop()

    profile = st.user.to_dict()
    email = str(profile.get("email", "")).strip().casefold()
    if email not in emails or profile.get("email_verified") is False:
        st.title("NEXUS")
        st.error("This account is not authorized for this private workspace.")
        st.button("Sign out", on_click=st.logout)
        st.stop()
    subject = str(profile.get("sub") or email)
    display_name = str(profile.get("name") or profile.get("given_name") or email.partition("@")[0])
    return Identity(subject, email, display_name)

