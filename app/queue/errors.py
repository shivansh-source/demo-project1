class DeferJob(Exception):
    """Raised by a handler to run the job again later without consuming an attempt."""

    def __init__(self, delay_seconds: float, reason: str = "") -> None:
        super().__init__(reason or f"deferred for {delay_seconds}s")
        self.delay_seconds = delay_seconds


class PermanentJobError(Exception):
    """Raised (or mixed into an exception) when retrying cannot help, e.g. the CRM rejected the
    data or the token. The job fails immediately instead of retrying with backoff."""
