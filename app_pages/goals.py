import streamlit as st
from nexus.ui.views import goals_page

goals_page(st.session_state["nexus_owner_id"])
