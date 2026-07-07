"""
dashboard/app_v2.py — SG Liveability v2
Serves sg_liveability.html via Streamlit (fixes CORS for local file)
Run: streamlit run dashboard/app_v2.py --server.port 8502
"""
import streamlit as st
import streamlit.components.v1 as components
from pathlib import Path

st.set_page_config(
    page_title="SG Liveability Index",
    page_icon="🏙️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding: 0 !important; max-width: 100% !important; }
section[data-testid="stSidebar"] { display: none; }
iframe { border: none !important; display: block; }
.stApp { background: #080e1c; }
</style>
""", unsafe_allow_html=True)

html_path = Path(__file__).parent / "sg_liveability.html"
if html_path.exists():
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    components.html(html, height=1800, scrolling=True)
else:
    st.error("sg_liveability.html not found in dashboard/ folder!")
