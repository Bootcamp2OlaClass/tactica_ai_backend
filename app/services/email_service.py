import sys
from abc import ABC, abstractmethod


class EmailService(ABC):
    @abstractmethod
    def send(self, to: str, subject: str, body: str) -> None:
        ...


class ConsoleEmailService(EmailService):
    """Interim dev-mode email backend — prints instead of sending.

    Real delivery (Resend or similar) is scheduled for Phase 13; this keeps
    password-reset/email-verification flows fully functional in dev/test
    without a paid provider, behind the same interface a real one would use.

    Deliberately writes to stdout directly rather than through the app's
    `logging` module: `app.core.logging`'s sanitizer redacts any "token: ..."
    pattern in real log output (correct there — see SENSITIVE_KEYS), but
    this "email" only exists to expose that exact token to a developer, so
    routing it through the same sanitizer would silently break it.
    """

    def send(self, to: str, subject: str, body: str) -> None:
        sys.stdout.write(
            f"\n----- DEV EMAIL (to={to}) -----\n"
            f"Subject: {subject}\n\n"
            f"{body}\n"
            f"--------------------------------\n\n"
        )
        sys.stdout.flush()


_email_service: EmailService = ConsoleEmailService()


def get_email_service() -> EmailService:
    return _email_service
