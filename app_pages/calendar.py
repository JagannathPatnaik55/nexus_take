import streamlit as st
from nexus.ui.views import calendar_page

calendar_page(st.session_state["nexus_owner_id"])
