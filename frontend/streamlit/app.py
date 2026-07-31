import streamlit as st

pages = [
    st.Page("views/home.py", title="Login/Logout", icon=":material/login:"),
    st.Page("views/documents.py", title="Documents", icon=":material/folder:"),
    st.Page("views/chat.py", title="Chat", icon=":material/chat:"),
]

navigation = st.navigation(pages)
navigation.run()