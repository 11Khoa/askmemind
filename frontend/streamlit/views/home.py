import streamlit as st

from api_client import ApiClient, ApiError

def get_default_api_base_url() -> str:
    return st.secrets.get(
        "ASKMEMIND_API_BASE_URL",
        "http://127.0.0.1:8000",
    )

DEFAULT_API_BASE_URL = get_default_api_base_url()


def init_session_state() -> None:
    if "api_base_url" not in st.session_state:
        st.session_state["api_base_url"] = DEFAULT_API_BASE_URL

    if "access_token" not in st.session_state:
        st.session_state["access_token"] = None

    if "current_user" not in st.session_state:
        st.session_state["current_user"] = None

    if "selected_document_id" not in st.session_state:
        st.session_state["selected_document_id"] = None

    if "selected_chat_id" not in st.session_state:
        st.session_state["selected_chat_id"] = None


def get_api_client(
    access_token: str | None = None,
) -> ApiClient:
    token = access_token

    if token is None:
        token = st.session_state.get("access_token")

    return ApiClient(
        api_base_url=st.session_state["api_base_url"],
        access_token=token,
    )


def is_authenticated() -> bool:
    return bool(st.session_state.get("access_token"))


def logout() -> None:
    st.session_state["access_token"] = None
    st.session_state["current_user"] = None
    st.session_state["selected_document_id"] = None
    st.session_state["selected_chat_id"] = None


def render_sidebar() -> None:
    with st.sidebar:
        # st.subheader("AskMeMind")

        api_base_url = st.session_state["api_base_url"]
        st.session_state["api_base_url"] = api_base_url.rstrip("/")

        if is_authenticated():
            current_user = st.session_state.get("current_user")

            if current_user:
                st.caption(f"Signed in as {current_user['email']}")

            if st.button("Logout", use_container_width=True):
                logout()
                st.rerun()


def render_login_tab() -> None:
    with st.form("login_form"):
        email = st.text_input("Email", key="login_email")
        password = st.text_input(
            "Password",
            type="password",
            key="login_password",
        )
        submitted = st.form_submit_button(
            "Login",
            use_container_width=True,
        )

    if not submitted:
        return

    if not email or not password:
        st.error("Email and password are required.")
        return

    try:
        client = get_api_client(access_token=None)
        token_response = client.login_user(
            email=email,
            password=password,
        )

        access_token = token_response["access_token"]

        authenticated_client = get_api_client(access_token=access_token)
        current_user = authenticated_client.get_me()

        st.session_state["access_token"] = access_token
        st.session_state["current_user"] = current_user

        st.success("Logged in successfully.")
        st.rerun()

    except ApiError as error:
        st.error(error.message)


def render_register_tab() -> None:
    with st.form("register_form"):
        email = st.text_input("Email", key="register_email")
        password = st.text_input(
            "Password",
            type="password",
            key="register_password",
        )
        submitted = st.form_submit_button(
            "Create account",
            use_container_width=True,
        )

    if not submitted:
        return

    if not email or not password:
        st.error("Email and password are required.")
        return

    try:
        client = get_api_client(access_token=None)

        client.register_user(
            email=email,
            password=password,
        )

        token_response = client.login_user(
            email=email,
            password=password,
        )

        access_token = token_response["access_token"]

        authenticated_client = get_api_client(access_token=access_token)
        current_user = authenticated_client.get_me()

        st.session_state["access_token"] = access_token
        st.session_state["current_user"] = current_user

        st.success("Account created and logged in.")
        st.rerun()

    except ApiError as error:
        st.error(error.message)


def render_auth_page() -> None:
    st.title("AskMeMind")
    st.caption("Upload PDFs and chat with document-grounded answers.")

    login_tab, register_tab = st.tabs(["Login", "Register"])

    with login_tab:
        render_login_tab()

    with register_tab:
        render_register_tab()


def render_home_page() -> None:
    st.title("AskMeMind")
    st.caption("Backend-first PDF RAG assistant.")

    st.write("Use the sidebar pages to upload documents and chat with your PDFs.")

    selected_document_id = st.session_state.get("selected_document_id")
    selected_chat_id = st.session_state.get("selected_chat_id")

    col1, col2 = st.columns(2)

    with col1:
        st.metric(
            label="Selected document",
            value="Ready" if selected_document_id else "None",
        )

    with col2:
        st.metric(
            label="Selected chat",
            value="Ready" if selected_chat_id else "None",
        )


def main() -> None:
    st.set_page_config(
        page_title="AskMeMind",
        page_icon="AM",
        layout="wide",
    )

    init_session_state()
    render_sidebar()

    if not is_authenticated():
        render_auth_page()
        return

    render_home_page()


if __name__ == "__main__":
    main()