from __future__ import annotations

import uvicorn

from .settings import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "trading_ai.api.app:create_app",
        host=settings.api.host,
        port=settings.api.port,
        factory=True,
        reload=False,
    )


if __name__ == "__main__":
    main()
