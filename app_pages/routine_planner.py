import streamlit as st
from nexus.ui.views import routine_planner

routine_planner(st.session_state["nexus_owner_id"])
