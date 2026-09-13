"""Launch Zenith: uvicorn on the configured host/port."""
from __future__ import annotations

import uvicorn

from zenith.core.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "zenith.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )