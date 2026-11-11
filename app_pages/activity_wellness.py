import streamlit as st
from nexus.ui.views import activity_wellness

activity_wellness(st.session_state["nexus_owner_id"])
