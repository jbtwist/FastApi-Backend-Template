class MailError(Exception):
    pass


class EmailOutboxEntryNotFound(MailError):
    pass
