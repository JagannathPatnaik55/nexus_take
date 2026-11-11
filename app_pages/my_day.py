import streamlit as st
from nexus.ui.views import my_day

my_day(st.session_state["nexus_owner_id"])
