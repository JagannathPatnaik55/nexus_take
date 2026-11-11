import streamlit as st
from nexus.ui.views import analytics_page

analytics_page(st.session_state["nexus_owner_id"])
