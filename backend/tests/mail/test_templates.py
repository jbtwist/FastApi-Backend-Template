from datetime import timedelta

from backend.mail.templates import (
    humanize_duration,
    render_oauth_link_email,
    render_password_reset_email,
    render_verification_email,
)


class TestRenderVerificationEmail:
    def test_includes_confirm_email_url_in_html_and_text(self):
        rendered = render_verification_email(
            confirm_email_url="https://app.backend-template.local/confirm-email?token=raw-token"
        )

        assert "https://app.backend-template.local/confirm-email?token=raw-token" in rendered.html
        assert "https://app.backend-template.local/confirm-email?token=raw-token" in rendered.text

    def test_has_a_non_empty_subject(self):
        rendered = render_verification_email(confirm_email_url="https://example.com")

        assert rendered.subject

    def test_html_escapes_special_characters_in_the_url(self):
        rendered = render_verification_email(confirm_email_url="https://example.com?a=1&b=2")

        assert "https://example.com?a=1&amp;b=2" in rendered.html
        assert "https://example.com?a=1&b=2" in rendered.text


class TestRenderPasswordResetEmail:
    def test_includes_reset_url_in_html_and_text(self):
        url = "https://app.backend-template.local/reset-password?token=raw-token"
        rendered = render_password_reset_email(reset_password_url=url, expires_in="1 hour")

        assert url in rendered.html
        assert url in rendered.text

    def test_states_the_expiry_window(self):
        rendered = render_password_reset_email(
            reset_password_url="https://example.com", expires_in="15 minutes"
        )

        assert "15 minutes" in rendered.html
        assert "15 minutes" in rendered.text

    def test_has_the_password_reset_subject(self):
        rendered = render_password_reset_email(
            reset_password_url="https://example.com", expires_in="1 hour"
        )

        assert rendered.subject == "Reset your Backend Template password"

    def test_does_not_leak_a_password(self):
        rendered = render_password_reset_email(
            reset_password_url="https://example.com", expires_in="1 hour"
        )

        assert "password" in rendered.text.lower()

    def test_html_escapes_special_characters_in_the_url(self):
        rendered = render_password_reset_email(
            reset_password_url="https://example.com?a=1&b=2", expires_in="1 hour"
        )

        assert "https://example.com?a=1&amp;b=2" in rendered.html
        assert "https://example.com?a=1&b=2" in rendered.text


class TestRenderOAuthLinkEmail:
    URL = "https://app.backend-template.local/link-provider-confirm?token=raw-token"

    def test_includes_the_confirm_url_in_html_and_text(self):
        rendered = render_oauth_link_email(link_provider_confirm_url=self.URL, expires_in="1 hour")

        assert self.URL in rendered.html
        assert self.URL in rendered.text

    def test_states_the_expiry_window(self):
        rendered = render_oauth_link_email(
            link_provider_confirm_url=self.URL, expires_in="15 minutes"
        )

        assert "15 minutes" in rendered.html
        assert "15 minutes" in rendered.text

    def test_has_the_oauth_link_subject(self):
        rendered = render_oauth_link_email(link_provider_confirm_url=self.URL, expires_in="1 hour")

        assert rendered.subject == "Confirm signing in to Backend Template with another provider"

    def test_tells_the_reader_to_ignore_it_if_they_did_not_ask(self):
        rendered = render_oauth_link_email(link_provider_confirm_url=self.URL, expires_in="1 hour")

        assert "ignore" in rendered.text.lower()

    def test_html_escapes_special_characters_in_the_url(self):
        rendered = render_oauth_link_email(
            link_provider_confirm_url="https://example.com?a=1&b=2", expires_in="1 hour"
        )

        assert "https://example.com?a=1&amp;b=2" in rendered.html
        assert "https://example.com?a=1&b=2" in rendered.text


class TestHumanizeDuration:
    def test_one_hour(self):
        assert humanize_duration(timedelta(hours=1)) == "1 hour"

    def test_multiple_hours(self):
        assert humanize_duration(timedelta(hours=24)) == "24 hours"

    def test_minutes(self):
        assert humanize_duration(timedelta(minutes=15)) == "15 minutes"

    def test_one_minute(self):
        assert humanize_duration(timedelta(minutes=1)) == "1 minute"
