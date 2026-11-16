"""Worker entrypoint: `python -m app.worker`. An RQ worker on the configured queue.

RQ forks a work-horse per job (Linux/macOS/Docker) and handles SIGTERM itself: the current job
finishes, then the worker exits. Retries, backoff and abandoned-job recovery are RQ's."""

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.queue.client import get_connection, get_queue
from app.queue.runtime import build_runtime


def main() -> None:
    from rq import Worker

    settings = get_settings()
    configure_logging(settings.log_level)
    build_runtime()  # fail fast on bad config (e.g. REASONING_ENABLED without a key)
    worker = Worker([get_queue()], connection=get_connection())
    worker.work(with_scheduler=True)  # the scheduler releases backed-off retries and deferrals


if __name__ == "__main__":
    main()
