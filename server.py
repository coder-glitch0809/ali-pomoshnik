"""Web entrypoint: persistent runtime or lightweight Vercel gateway."""
import os

if os.getenv("VERCEL") == "1":
    from gateway import app
else:
    from runtime import app

if __name__ == "__main__":
    import runpy
    runpy.run_module("runtime", run_name="__main__")
