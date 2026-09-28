"""The app's single, fail-closed backend integration point."""

from __future__ import annotations

import streamlit as st

from hackowatt_stage11.loader import load_real_data
from hackowatt_stage11.models import WattWiseData


@st.cache_data(ttl=None, show_spinner="Loading WattWise Home...")
def get_data() -> WattWiseData:
    """Return only real frozen backend data; never fall back to a mock."""
    return load_real_data()
