class AuthError(Exception):
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


class EmailNotVerified(AuthError):
    pass


class InvalidVerificationToken(AuthError):
    pass


class VerificationTokenExpired(AuthError):
    pass


class InvalidPasswordResetToken(AuthError):
    pass


class PasswordResetTokenExpired(AuthError):
    pass


class PasswordTooShort(AuthError):
    pass


class PasswordTooLong(AuthError):
    pass


class PasswordCompromised(AuthError):
    pass
