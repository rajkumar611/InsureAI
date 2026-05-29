"""
Launcher for the AI Underwriting API server.

We own the event loop creation so psycopg3 async gets a SelectorEventLoop,
not the Windows-default ProactorEventLoop which psycopg3 cannot use.
"""
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn

if __name__ == "__main__":
    config = uvicorn.Config("backend.main:app", host="0.0.0.0", port=8081, reload=False)
    server = uvicorn.Server(config)
    asyncio.run(server.serve())
