"""Single-worker launcher: ``uv run python -m app``.

The worker count is the literal 1 on purpose. NiceGUI keeps per-client state in-process and
the Realtime hub fans events out in-process, so a second worker would miss updates.
"""

import logging

import uvicorn

from app.main import create_app
from app.settings import Settings


def main() -> None:
    settings = Settings()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    logging.getLogger("quadra").info("Quadra starting on %s (single worker)", settings.app_base_url)
    uvicorn.run(
        create_app,
        factory=True,
        host=settings.app_host,
        port=settings.app_port,
        workers=1,
    )


if __name__ == "__main__":
    main()
