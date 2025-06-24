import streamlit as st

if "page" not in st.session_state:
    st.session_state.page = "main"

def load_page(page_name):
    with open(page_name, "r", encoding="utf-8") as f:
        code = f.read()
    exec(code, globals())

if st.session_state.page == "main":
    st.set_page_config(page_title="Car Price", layout="centered")
    st.title("🚗 - Car Price Analysis")
    st.write("Jenis mobil yang ingin dianalisis:")

    if st.button("Mobil Bekas"):
        st.session_state.page = "app_openai_user.py"
        st.rerun()

    if st.button("Mobil Baru"):
        st.session_state.page = "newcar.py"
        st.rerun()

elif st.session_state.page in ["app_openai_user.py", "newcar.py"]:
    load_page(st.session_state.page)