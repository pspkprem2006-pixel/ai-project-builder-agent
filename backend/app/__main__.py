"""Run the API server on the configured ``BACKEND_PORT``.

Usage (honors your .env ``BACKEND_PORT`` so you can run many projects on
different ports in parallel):

    python -m app                 # uses BACKEND_PORT (default 8010)
    # or, equivalent:
    uvicorn app.main:app --port 8010

In Docker the same setting is read by the entrypoint, so you can also do:
    docker run -e BACKEND_PORT=8021 ...
"""
from __future__ import annotations

import uvicorn

from app.config import get_settings

if __name__ == "__main__":
    port = get_settings().BACKEND_PORT
    uvicorn.run(app="app.main:app", host="0.0.0.0", port=port)
