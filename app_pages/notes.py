import streamlit as st
from nexus.ui.views import notes_page

notes_page(st.session_state["nexus_owner_id"])
