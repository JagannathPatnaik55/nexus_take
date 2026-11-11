import streamlit as st
from nexus.ui.views import study_center

study_center(st.session_state["nexus_owner_id"])
