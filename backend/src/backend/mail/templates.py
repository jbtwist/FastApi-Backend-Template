from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

_TEMPLATES_DIR = Path(__file__).parent / "email_templates"
_env = Environment(
    loader=FileSystemLoader(_TEMPLATES_DIR),
    autoescape=lambda name: bool(name) and name.endswith(".html.jinja"),
)

VERIFICATION_EMAIL_SUBJECT = "Welcome to Todoapp - confirm your email"
PASSWORD_RESET_EMAIL_SUBJECT = "Reset your Todoapp password"


@dataclass
class RenderedEmail:
    subject: str
    html: str
    text: str


def humanize_duration(td: timedelta) -> str:
    """Render a link lifetime for email copy: "1 hour", "24 hours", "15 minutes"."""
    total_seconds = int(td.total_seconds())
    if total_seconds % 3600 == 0:
        hours = total_seconds // 3600
        return f"{hours} hour" if hours == 1 else f"{hours} hours"
    minutes = max(1, round(total_seconds / 60))
    return f"{minutes} minute" if minutes == 1 else f"{minutes} minutes"


def render_verification_email(*, confirm_email_url: str) -> RenderedEmail:
    html = _env.get_template("verification_email.html.jinja").render(
        confirm_email_url=confirm_email_url
    )
    text = _env.get_template("verification_email.txt.jinja").render(
        confirm_email_url=confirm_email_url
    )
    return RenderedEmail(subject=VERIFICATION_EMAIL_SUBJECT, html=html, text=text)


def render_password_reset_email(*, reset_password_url: str, expires_in: str) -> RenderedEmail:
    context = {"reset_password_url": reset_password_url, "expires_in": expires_in}
    html = _env.get_template("password_reset_email.html.jinja").render(**context)
    text = _env.get_template("password_reset_email.txt.jinja").render(**context)
    return RenderedEmail(subject=PASSWORD_RESET_EMAIL_SUBJECT, html=html, text=text)
