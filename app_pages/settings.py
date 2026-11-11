import streamlit as st
from nexus.ui.views import settings_page

settings_page(st.session_state["nexus_owner_id"])
