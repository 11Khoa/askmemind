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


def format_file_size(size_bytes: int | None) -> str:
    if size_bytes is None:
        return "Unknown"

    if size_bytes < 1024:
        return f"{size_bytes} B"

    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"

    return f"{size_bytes / (1024 * 1024):.1f} MB"


def document_title(document: dict) -> str:
    return document.get("original_filename") or document.get("filename") or "Untitled document"


def document_option_label(document: dict) -> str:
    title = document_title(document)
    status = document.get("status", "unknown")
    pages = document.get("page_count")

    if pages:
        return f"{title} - {status} - {pages} pages"

    return f"{title} - {status}"


def render_document_summary(document: dict) -> None:
    title = document_title(document)
    status = document.get("status", "unknown")
    page_count = document.get("page_count") or "Unknown"
    file_size = format_file_size(document.get("file_size_bytes"))

    st.markdown(f"### {title}")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Status", status)

    with col2:
        st.metric("Pages", page_count)

    with col3:
        st.metric("Size", file_size)

    with st.expander("Technical details"):
        st.write(f"Document ID: `{document['id']}`")
        st.write(f"Source type: `{document.get('source_type')}`")
        st.write(f"Content type: `{document.get('content_type')}`")
        st.write(f"Stored filename: `{document.get('filename')}`")


st.set_page_config(page_title="Documents", page_icon="Docs", layout="wide")
st.title("Documents")
st.caption("Upload PDFs, review processing status, and choose the active document for chat.")

require_auth()

client = get_client()

with st.container():
    st.subheader("Upload a PDF")

    uploaded_file = st.file_uploader(
        "PDF file",
        type=["pdf"],
        help="Upload a text-based PDF. Scanned PDFs without selectable text are not supported yet.",
    )

    if uploaded_file is not None:
        col1, col2 = st.columns([1, 3])

        with col1:
            upload_clicked = st.button("Upload and process", use_container_width=True)

        with col2:
            st.caption("Processing runs synchronously in the current MVP and may take a moment.")

        if upload_clicked:
            try:
                with st.spinner("Uploading, extracting text, chunking, and generating embeddings..."):
                    document = client.upload_document(
                        file_name=uploaded_file.name,
                        file_bytes=uploaded_file.getvalue(),
                        content_type="application/pdf",
                    )

                st.session_state["selected_document_id"] = str(document["id"])
                st.success("Document is ready for chat.")
                st.rerun()

            except ApiError as error:
                st.error(error.message)

st.divider()

st.subheader("Document library")

try:
    documents = client.list_documents()
except ApiError as error:
    st.error(error.message)
    st.stop()

if not documents:
    st.info("No documents yet. Upload a PDF to start.")
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
    "Active document for chat",
    options=list(document_options.keys()),
    index=default_index,
)

st.session_state["selected_document_id"] = document_options[selected_label]

selected_document = next(
    document
    for document in documents
    if str(document["id"]) == st.session_state["selected_document_id"]
)

render_document_summary(selected_document)