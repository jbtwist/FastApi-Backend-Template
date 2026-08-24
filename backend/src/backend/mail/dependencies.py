from typing import Annotated

from fastapi import Depends

from backend.database import DbDep
from backend.mail.repository import SqlEmailOutboxRepository


def get_email_outbox_repo(db: DbDep) -> SqlEmailOutboxRepository:
    return SqlEmailOutboxRepository(db)


EmailOutboxRepoDep = Annotated[SqlEmailOutboxRepository, Depends(get_email_outbox_repo)]
