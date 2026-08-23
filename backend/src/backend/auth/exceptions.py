class AuthError(Exception):
    pass


class EmailAlreadyRegistered(AuthError):
    pass


class InvalidCredentials(AuthError):
    pass


class InvalidAccessToken(AuthError):
    pass


class AccessTokenExpired(AuthError):
    pass


class InvalidRefreshToken(AuthError):
    pass


class RefreshTokenExpired(AuthError):
    pass


class RefreshTokenReuseDetected(AuthError):
    pass
