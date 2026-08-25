from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

_TEMPLATES_DIR = Path(__file__).parent / "email_templates"
_env = Environment(
    loader=FileSystemLoader(_TEMPLATES_DIR),
    autoescape=lambda name: bool(name) and name.endswith(".html.jinja"),
)

VERIFICATION_EMAIL_SUBJECT = "Welcome to Todoapp - confirm your email"


@dataclass
class RenderedEmail:
    subject: str
    html: str
    text: str


def render_verification_email(*, confirm_email_url: str) -> RenderedEmail:
    html = _env.get_template("verification_email.html.jinja").render(
        confirm_email_url=confirm_email_url
    )
    text = _env.get_template("verification_email.txt.jinja").render(
        confirm_email_url=confirm_email_url
    )
    return RenderedEmail(subject=VERIFICATION_EMAIL_SUBJECT, html=html, text=text)
