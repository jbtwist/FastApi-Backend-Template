from backend.mail.templates import render_verification_email


class TestRenderVerificationEmail:
    def test_includes_confirm_email_url_in_html_and_text(self):
        rendered = render_verification_email(
            confirm_email_url="https://app.todoapp.local/confirm-email?token=raw-token"
        )

        assert "https://app.todoapp.local/confirm-email?token=raw-token" in rendered.html
        assert "https://app.todoapp.local/confirm-email?token=raw-token" in rendered.text

    def test_has_a_non_empty_subject(self):
        rendered = render_verification_email(confirm_email_url="https://example.com")

        assert rendered.subject

    def test_html_escapes_special_characters_in_the_url(self):
        rendered = render_verification_email(
            confirm_email_url="https://example.com?a=1&b=2"
        )

        assert "https://example.com?a=1&amp;b=2" in rendered.html
        assert "https://example.com?a=1&b=2" in rendered.text
