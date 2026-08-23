import os

os.environ.setdefault("RATE_LIMIT_REDIS_URL", "memory://")
os.environ.setdefault("RATE_LIMIT_REGISTER_LIMIT", "3/minute")
os.environ.setdefault("RATE_LIMIT_LOGIN_LIMIT", "3/minute")
os.environ.setdefault("RATE_LIMIT_REFRESH_LIMIT", "3/minute")
os.environ.setdefault("RATE_LIMIT_LOGOUT_LIMIT", "3/minute")
