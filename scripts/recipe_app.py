import streamlit as st
import requests
import os


API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")
# -----------------------
# Page config
# -----------------------
st.set_page_config(
    page_title="Historic Recipe Explorer",
    page_icon="🍲",
    layout="wide"
)

# -----------------------
# Custom CSS
# -----------------------
st.markdown("""
<style>

/* =========================
   BACKGROUND
   ========================= */
.stApp {
    background-color: #f7f3ec;
    background-image: url("https://images.unsplash.com/vector-1761241810096-982ff36403b7?q=80&w=2068&auto=format&fit=crop&ixlib=rb-4.1.0");
    background-size: cover;
    background-position: center;
    background-attachment: fixed;
}

.stApp::before {
    content: "";
    position: fixed;
    top: 0;
    left: 0;
    height: 100%;
    width: 100%;
    background: rgba(247, 243, 236, 0.55);
    z-index: -1;
}

/* =========================
   HERO INFO BOX
   ========================= */
.info-box {
    background-color: rgba(255, 255, 255, 0.96);
    border-left: 8px solid #7b241c;
    padding: 26px;
    border-radius: 14px;

    /* MORE SPACE BELOW TITLE */
    margin-bottom: 70px;

    box-shadow: 0px 4px 12px rgba(0,0,0,0.10);
}

.info-box h1 {
    color: #7b241c;
    margin-bottom: 6px;
    font-size: 3rem;
}

.subtitle {
    color: #5d4037;
    font-size: 1.1rem;
}

/* =========================
   SEARCH CARD (TITLE)
   ========================= */
.search-card {
    background-color: rgba(255, 255, 255, 0.97);
    border-left: 8px solid #3f6ea5;
    padding: 14px 18px;

    /* SMALL GAP ABOVE INPUT */
    margin-bottom: 2px;

    border-radius: 14px;
    box-shadow: 0px 3px 10px rgba(0,0,0,0.08);
}

.search-title {
    font-size: 2.4rem;
    font-weight: 700;
    color: #2c3e50;
    line-height: 1.2;
}

/* =========================
   SEARCH WRAPPER
   ========================= */
.search-wrapper {
    width: 90%;
    margin: 0 auto 6px auto;  /* tighter bottom spacing */
}

/* =========================
   INPUT FIELD
   ========================= */
.stTextInput input {
    background-color: rgba(245, 249, 253, 0.98);
    border-radius: 10px;
    padding: 12px;
    box-shadow: inset 0 1px 2px rgba(0,0,0,0.04);
}

.stTextInput {
    margin-top: -10px;  /*  pulls input closer to title */
}

/* =========================
   BUTTON
   ========================= */
.stButton button {
    background-color: #7b241c;
    color: white;
    border-radius: 10px;
    height: 3em;
    border: none;
    font-size: 16px;
    font-weight: 600;
}

.stButton button:hover {
    background-color: #922b21;
}

/* =========================
   CHAT BUBBLES
   ========================= */
[data-testid="stChatMessage"] {
    background-color: rgba(255, 255, 255, 0.92);
    padding: 1rem;
    border-radius: 12px;
    box-shadow: 0px 3px 10px rgba(0,0,0,0.08);
}

/* remove default Streamlit spacing noise */
.element-container {
    margin-bottom: 0px !important;
}

</style>
""", unsafe_allow_html=True)

# -----------------------
# HERO HEADER
# -----------------------
st.markdown("""
<div class="info-box">

<h1>🍲 Historic Recipe Explorer</h1>

<p class="subtitle">
Discover recipes, ingredients, and culinary traditions from historic American cookbooks.
</p>

<hr style="border: none; border-top: 1px solid #e0d6c8; margin: 12px 0;">

<p>
<b>The Feeding America: The Historic American Cookbook Project</b>,
created by Michigan State University, preserves 76 American cookbooks
published between the late 18th and early 20th centuries.
</p>

<p>
This application transforms those historic cookbooks into an
interactive, AI-powered research experience.
</p>

<p>
Discover how Americans cooked, baked, and entertained in the
1800s and early 1900s.
</p>

<b>Try asking:</b>

<ul>
<li>What were common breakfast dishes in the early days?</li>
<li>What kinds of coffee drinks were popular in old recipes?</li>
<li>What fruit cocktails were traditionally made?</li>
<li>How was chicken soup prepared?</li>
<li>What were some traditional bread loaf recipes?</li>
</ul>

</div>
""", unsafe_allow_html=True)

# -----------------------
# SEARCH SECTION
# -----------------------
st.markdown("""
<div class="search-card">
    <div class="search-title">
        🔍 Ask a question about historic recipes 🥕 🌽 🥔 🧄
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown('<div class="search-wrapper">', unsafe_allow_html=True)

left, center, right = st.columns([1, 8, 1])

with center:
    question = st.text_input(
        label="",
        placeholder="Search historic recipes, ingredients, or dishes...",
        
        icon="🔍"
    )

st.markdown('</div>', unsafe_allow_html=True)

# -----------------------
# SEARCH LOGIC
# -----------------------
if question:

    with st.chat_message("user"):
        st.write(question)

    with st.spinner("Searching historic cookbooks..."):

        try:
            response = requests.post(
                f"{API_URL}/ask",
                json={"question": question},
                timeout=30
            )
            response.raise_for_status()

            data = response.json()

            with st.chat_message("assistant"):
                st.markdown(data["answer"])

        except Exception as e:
            st.error(f"Unable to retrieve recipes. Error: {e}")