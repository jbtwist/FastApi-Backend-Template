import subprocess
import sys


def test_importing_celery_app_alone_registers_user_table():
    """Regression: importing only mail.celery_app must still resolve the outbox->user FK."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from backend.database import Base; import backend.mail.celery_app; "
            "assert 'user' in Base.metadata.tables",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
