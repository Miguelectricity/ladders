import logging
import sys

PACKAGE_LOGGER = "backend"
LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"


def configure_logging(level: int = logging.INFO) -> None:
    """Attach a handler to the `backend` logger so its records actually appear.

    Configured on our own package rather than the root logger: uvicorn owns the
    root config when it serves the app, and without a handler of our own every
    `logger.info` below WARNING is discarded silently. Idempotent, so calling it
    again from a test or a second entry point does not double up output.
    """
    logger = logging.getLogger(PACKAGE_LOGGER)
    if logger.handlers:
        return

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(handler)
    logger.setLevel(level)
    # Ours to emit; don't hand records to the root logger a second time.
    logger.propagate = False
