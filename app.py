"""Vercel entrypoint: Vercel looks for a top-level FastAPI `app`. Routes come from the stateless gateway."""
from gateway import app  # noqa: F401
