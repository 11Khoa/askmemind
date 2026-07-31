import streamlit as st

from api_client import ApiClient, ApiError


def get_client() -> ApiClient:
    return ApiClient(
        api_base_url=st.session_state["api_base_url"],
        access_token=st.session_state["access_token"],
    )


def require_auth() -> None:
    if not st.session_state.get("access_token"):
        st.warning("Please login first.")
        st.stop()


def document_title(document: dict) -> str:
    return document.get("original_filename") or document.get("filename") or "Untitled document"


def chat_label(chat: dict) -> str:
    title = chat.get("title") or "Untitled chat"
    created_at = chat.get("created_at")

    if created_at:
        return f"{title} - {created_at[:10]}"

    return title


def get_selected_document(
    client: ApiClient,
    document_id: str,
) -> dict | None:
    try:
        return client.get_document(document_id=document_id)
    except ApiError:
        return None


def render_active_document(document: dict | None) -> None:
    if document is None:
        st.warning("No active document selected. Go to Documents and choose a PDF before chatting.")
        st.stop()

    title = document_title(document)
    status = document.get("status", "unknown")
    page_count = document.get("page_count")

    st.markdown(f"### {title}")

    details = [f"Status: {status}"]

    if page_count:
        details.append(f"Pages: {page_count}")

    st.caption(" - ".join(details))


def render_citations(citations: list[dict]) -> None:
    if not citations:
        return

    with st.expander("Sources"):
        for citation in citations:
            source = citation.get("source_number")
            page = citation.get("page_number")
            chunk_index = citation.get("chunk_index")
            distance = citation.get("distance")

            parts = [f"Source {source}"]

            if page is not None:
                parts.append(f"Page {page}")

            if chunk_index is not None:
                parts.append(f"Chunk {chunk_index}")

            if distance is not None:
                parts.append(f"Distance {distance:.4f}")

            st.caption(" - ".join(parts))


def render_message(message: dict) -> None:
    role = message.get("role", "assistant")
    content = message.get("content", "")

    with st.chat_message(role):
        st.write(content)

        metadata = message.get("message_metadata") or {}
        citations = metadata.get("citations") or []
        render_citations(citations)


def render_chat_selector(client: ApiClient) -> str | None:
    header_col, button_col = st.columns([3, 1])

    with header_col:
        st.subheader("Chat workspace")

    try:
        chats = client.list_chats()
    except ApiError as error:
        st.error(error.message)
        st.stop()

    with st.form("create_chat_form"):
        title = st.text_input("New chat title", placeholder="Example: Q&A about policy PDF")
        submitted = st.form_submit_button("Create new chat", use_container_width=True)

    if submitted:
        try:
            chat = client.create_chat(title=title or None)
            st.session_state["selected_chat_id"] = str(chat["id"])
            st.success("Chat created.")
            st.rerun()
        except ApiError as error:
            st.error(error.message)

    if not chats:
        st.info("Create a chat to start asking questions.")
        return None

    chat_options = {
        chat_label(chat): str(chat["id"])
        for chat in chats
    }

    selected_chat_id = st.session_state.get("selected_chat_id")
    option_values = list(chat_options.values())

    default_index = 0
    if selected_chat_id in option_values:
        default_index = option_values.index(selected_chat_id)

    selected_label = st.selectbox(
        "Active chat",
        options=list(chat_options.keys()),
        index=default_index,
    )

    st.session_state["selected_chat_id"] = chat_options[selected_label]
    return st.session_state["selected_chat_id"]


def render_chat_history(client: ApiClient, chat_id: str) -> None:
    try:
        messages = client.list_messages(chat_id=chat_id)
    except ApiError as error:
        st.error(error.message)
        st.stop()

    if not messages:
        with st.chat_message("assistant"):
            st.write("Ask a question and I will answer using the selected PDF.")

    for message in messages:
        render_message(message)


def render_question_input(
    client: ApiClient,
    chat_id: str,
    document_id: str,
) -> None:
    question = st.chat_input("Ask a question about the active document")

    if not question:
        return

    with st.chat_message("user"):
        st.write(question)

    try:
        with st.spinner("Retrieving relevant chunks and generating an answer..."):
            client.ask_question(
                chat_id=chat_id,
                content=question,
                document_id=document_id,
                top_k=3,
            )

        st.rerun()

    except ApiError as error:
        st.error(error.message)


def document_option_label(document: dict) -> str:
    title = document_title(document)
    status = document.get("status", "unknown")
    page_count = document.get("page_count")

    if page_count:
        return f"{title} - {status} - {page_count} pages"

    return f"{title} - {status}"


def render_document_selector(client: ApiClient) -> dict | None:
    try:
        documents = client.list_documents()
    except ApiError as error:
        st.error(error.message)
        st.stop()

    if not documents:
        st.warning("No documents found. Upload a PDF from the Documents page first.")
        st.stop()

    document_options = {
        document_option_label(document): str(document["id"])
        for document in documents
    }

    selected_document_id = st.session_state.get("selected_document_id")
    option_values = list(document_options.values())

    default_index = 0
    if selected_document_id in option_values:
        default_index = option_values.index(selected_document_id)

    selected_label = st.selectbox(
        "Active document",
        options=list(document_options.keys()),
        index=default_index,
    )

    st.session_state["selected_document_id"] = document_options[selected_label]

    return next(
        document
        for document in documents
        if str(document["id"]) == st.session_state["selected_document_id"]
    )


st.set_page_config(page_title="Chat", page_icon="Chat", layout="wide")
st.title("Chat")
st.caption("Ask document-grounded questions using the active PDF selected from your library.")

require_auth()

client = get_client()
selected_document = render_document_selector(client)
selected_document_id = st.session_state["selected_document_id"]

render_active_document(selected_document)

st.divider()

left_col, right_col = st.columns([1, 2])

with left_col:
    selected_chat_id = render_chat_selector(client)

with right_col:
    if not selected_chat_id:
        st.stop()

    render_chat_history(client, selected_chat_id)
    render_question_input(
        client=client,
        chat_id=selected_chat_id,
        document_id=selected_document_id,
    )