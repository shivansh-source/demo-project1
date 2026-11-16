class DeferJob(Exception):
    """Raised by a handler to run the job again later without consuming an attempt."""

    def __init__(self, delay_seconds: float, reason: str = "") -> None:
        super().__init__(reason or f"deferred for {delay_seconds}s")
        self.delay_seconds = delay_seconds
