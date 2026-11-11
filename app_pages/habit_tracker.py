import streamlit as st
from nexus.ui.views import habit_tracker

habit_tracker(st.session_state["nexus_owner_id"])
