import streamlit as st
from nexus.ui.views import ai_assistant

ai_assistant(st.session_state["nexus_owner_id"])
