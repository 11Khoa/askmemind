import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urlencode, urlsplit, urlunsplit

from app.core.config import Settings


class ResetEmailService:
    def __init__(self, config: Settings):
        self.config = config

    def is_configured(self) -> bool:
        url = self.config.password_reset_url
        return bool(
            self.config.smtp_host
            and self.config.smtp_from_email
            and url
            and (url.scheme == "https" or url.host in {"localhost", "127.0.0.1"})
        )

    def send_reset(self, email: str, token: str) -> None:
        if not self.is_configured():
            raise RuntimeError("Password reset email is not configured")
        url = urlsplit(str(self.config.password_reset_url))
        # A fragment keeps the token out of HTTP access logs and Referer headers.
        link = urlunsplit(
            (url.scheme, url.netloc, url.path, url.query, urlencode({"token": token}))
        )
        message = EmailMessage()
        message["Subject"] = "Reset your AskMeMind password"
        message["From"] = self.config.smtp_from_email
        message["To"] = email
        message.set_content(
            f"Reset your password: {link}\n\n"
            f"This link expires in {self.config.password_reset_expire_minutes} minutes. "
            "If you did not request this, ignore this email.\n"
        )
        context = ssl.create_default_context()
        connection = smtplib.SMTP_SSL if self.config.smtp_use_ssl else smtplib.SMTP
        kwargs = {"context": context} if self.config.smtp_use_ssl else {}
        with connection(
            self.config.smtp_host, self.config.smtp_port, timeout=10, **kwargs
        ) as smtp:
            if not self.config.smtp_use_ssl:
                smtp.starttls(context=context)
            if self.config.smtp_username:
                smtp.login(
                    self.config.smtp_username,
                    self.config.smtp_password.get_secret_value(),
                )
            smtp.send_message(message)
