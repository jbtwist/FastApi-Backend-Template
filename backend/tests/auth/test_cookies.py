from backend.auth import cookies


class TestAccessTokenCookie:
    def test_sets_httponly(self, auth_config):
        params = cookies.access_token_cookie("a-jwt-value", config=auth_config)

        assert params["httponly"] is True

    def test_sets_samesite_lax(self, auth_config):
        params = cookies.access_token_cookie("a-jwt-value", config=auth_config)

        assert params["samesite"] == "lax"

    def test_scoped_to_root_path(self, auth_config):
        params = cookies.access_token_cookie("a-jwt-value", config=auth_config)

        assert params["path"] == "/"

    def test_max_age_matches_access_token_exp(self, auth_config):
        params = cookies.access_token_cookie("a-jwt-value", config=auth_config)

        assert params["max_age"] == int(auth_config.ACCESS_TOKEN_EXP.total_seconds())

    def test_secure_flag_follows_config(self, auth_config):
        params = cookies.access_token_cookie("a-jwt-value", config=auth_config)

        assert params["secure"] == auth_config.COOKIE_SECURE

    def test_carries_the_given_token_value(self, auth_config):
        params = cookies.access_token_cookie("a-jwt-value", config=auth_config)

        assert params["key"] == "access_token"
        assert params["value"] == "a-jwt-value"


class TestRefreshTokenCookie:
    def test_sets_httponly(self, auth_config):
        params = cookies.refresh_token_cookie("a-raw-refresh-value", config=auth_config)

        assert params["httponly"] is True

    def test_sets_samesite_lax(self, auth_config):
        params = cookies.refresh_token_cookie("a-raw-refresh-value", config=auth_config)

        assert params["samesite"] == "lax"

    def test_scoped_to_refresh_endpoint_path_not_root(self, auth_config):
        params = cookies.refresh_token_cookie("a-raw-refresh-value", config=auth_config)

        assert params["path"] == "/auth/refresh"

    def test_max_age_matches_refresh_token_exp(self, auth_config):
        params = cookies.refresh_token_cookie("a-raw-refresh-value", config=auth_config)

        assert params["max_age"] == int(auth_config.REFRESH_TOKEN_EXP.total_seconds())

    def test_secure_flag_follows_config(self, auth_config):
        params = cookies.refresh_token_cookie("a-raw-refresh-value", config=auth_config)

        assert params["secure"] == auth_config.COOKIE_SECURE

    def test_carries_the_given_token_value(self, auth_config):
        params = cookies.refresh_token_cookie("a-raw-refresh-value", config=auth_config)

        assert params["key"] == "refresh_token"
        assert params["value"] == "a-raw-refresh-value"


class TestClearAuthCookies:
    def test_clear_access_token_cookie_expires_immediately_on_root_path(self, auth_config):
        params = cookies.clear_access_token_cookie(config=auth_config)

        assert params["key"] == "access_token"
        assert params["max_age"] == 0
        assert params["path"] == "/"

    def test_clear_refresh_token_cookie_expires_immediately_on_refresh_path(self, auth_config):
        params = cookies.clear_refresh_token_cookie(config=auth_config)

        assert params["key"] == "refresh_token"
        assert params["max_age"] == 0
        assert params["path"] == "/auth/refresh"
