import logging
from abc import ABC, abstractmethod

logger = logging.getLogger("app.email")


class EmailService(ABC):
    @abstractmethod
    def send(self, to: str, subject: str, body: str) -> None:
        ...


class ConsoleEmailService(EmailService):
    """Interim dev-mode email backend — logs instead of sending.

    Real delivery (Resend or similar) is scheduled for Phase 13; this keeps
    password-reset/email-verification flows fully functional in dev/test
    without a paid provider, behind the same interface a real one would use.
    """

    def send(self, to: str, subject: str, body: str) -> None:
        logger.info(
            "email(to=%s, subject=%s):\n%s",
            to,
            subject,
            body,
        )


_email_service: EmailService = ConsoleEmailService()


def get_email_service() -> EmailService:
    return _email_service
