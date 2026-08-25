"""Import every domain's models module so Base.metadata is fully populated everywhere."""

from backend.auth import models as auth_models  # noqa: F401
from backend.mail import models as mail_models  # noqa: F401
