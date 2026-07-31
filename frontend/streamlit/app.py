import streamlit as st

pages = [
    st.Page("views/home.py", title="Home", icon=":material/home:"),
    st.Page("views/documents.py", title="Documents", icon=":material/folder:"),
    st.Page("views/chat.py", title="Chat", icon=":material/chat:"),
]

navigation = st.navigation(pages)
navigation.run()