import streamlit as st
from nexus.ui.views import finance_page

finance_page(st.session_state["nexus_owner_id"])
