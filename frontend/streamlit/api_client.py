from typing import Any

import requests


class ApiError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class ApiClient:
    def __init__(
        self,
        api_base_url: str,
        access_token: str | None = None,
    ) -> None:
        self.api_base_url = api_base_url.rstrip("/")
        self.access_token = access_token

    def _build_url(self, path: str) -> str:
        return f"{self.api_base_url}{path}"

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}

        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"

        return headers

    def _parse_error_message(self, response: requests.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return response.text or "Request failed."

        detail = payload.get("detail")

        if isinstance(detail, str):
            return detail

        if isinstance(detail, list):
            messages: list[str] = []

            for item in detail:
                if isinstance(item, dict):
                    message = item.get("msg")
                    location = item.get("loc")

                    if location:
                        messages.append(f"{location}: {message}")
                    elif message:
                        messages.append(str(message))
                else:
                    messages.append(str(item))

            return "; ".join(messages) if messages else "Request failed."

        return "Request failed."

    def _handle_response(self, response: requests.Response) -> Any:
        if response.ok:
            if not response.content:
                return None

            return response.json()

        raise ApiError(
            message=self._parse_error_message(response),
            status_code=response.status_code,
        )

    def register_user(
        self,
        email: str,
        password: str,
    ) -> dict[str, Any]:
        response = requests.post(
            self._build_url("/auth/register"),
            json={
                "email": email.lower(),
                "password": password,
            },
            timeout=30,
        )

        return self._handle_response(response)

    def login_user(
        self,
        email: str,
        password: str,
    ) -> dict[str, Any]:
        response = requests.post(
            self._build_url("/auth/login"),
            json={
                "email": email.lower(),
                "password": password,
            },
            timeout=30,
        )

        return self._handle_response(response)

    def get_me(self) -> dict[str, Any]:
        response = requests.get(
            self._build_url("/auth/me"),
            headers=self._headers(),
            timeout=30,
        )

        return self._handle_response(response)

    def upload_document(
        self,
        file_name: str,
        file_bytes: bytes,
        content_type: str = "application/pdf",
    ) -> dict[str, Any]:
        response = requests.post(
            self._build_url("/documents/upload"),
            headers=self._headers(),
            files={
                "file": (
                    file_name,
                    file_bytes,
                    content_type,
                )
            },
            timeout=120,
        )

        return self._handle_response(response)

    def list_documents(self) -> list[dict[str, Any]]:
        response = requests.get(
            self._build_url("/documents"),
            headers=self._headers(),
            timeout=30,
        )

        return self._handle_response(response)

    def get_document(
        self,
        document_id: str,
    ) -> dict[str, Any]:
        response = requests.get(
            self._build_url(f"/documents/{document_id}"),
            headers=self._headers(),
            timeout=30,
        )

        return self._handle_response(response)

    def create_chat(
        self,
        title: str | None = None,
    ) -> dict[str, Any]:
        response = requests.post(
            self._build_url("/chats"),
            headers=self._headers(),
            json={
                "title": title,
            },
            timeout=30,
        )

        return self._handle_response(response)

    def list_chats(self) -> list[dict[str, Any]]:
        response = requests.get(
            self._build_url("/chats"),
            headers=self._headers(),
            timeout=30,
        )

        return self._handle_response(response)

    def list_messages(
        self,
        chat_id: str,
    ) -> list[dict[str, Any]]:
        response = requests.get(
            self._build_url(f"/chats/{chat_id}/messages"),
            headers=self._headers(),
            timeout=30,
        )

        return self._handle_response(response)

    def ask_question(
        self,
        chat_id: str,
        content: str,
        document_id: str | None,
        top_k: int = 3,
    ) -> dict[str, Any]:
        response = requests.post(
            self._build_url(f"/chats/{chat_id}/questions"),
            headers=self._headers(),
            json={
                "content": content,
                "document_id": document_id,
                "top_k": top_k,
            },
            timeout=120,
        )

        return self._handle_response(response)