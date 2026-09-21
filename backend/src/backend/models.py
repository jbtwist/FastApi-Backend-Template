"""Import every domain's models so `Base.metadata` knows all the tables."""

from backend.auth import models as auth_models  # noqa: F401
from backend.auth.oauth import models as oauth_models  # noqa: F401
from backend.mail import models as mail_models  # noqa: F401
