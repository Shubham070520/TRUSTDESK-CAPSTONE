"""Entry point. ``python run.py`` or ``uvicorn run:app``."""
import uvicorn

from app import Application
from app.config import Config


class Server:
    """Starts the HTTP server for an already built ASGI app."""

    def __init__(self, asgi_app_path: str, host: str, port: int) -> None:
        self._asgi_app_path = asgi_app_path
        self._host = host
        self._port = port

    def start(self) -> None:
        uvicorn.run(self._asgi_app_path, host=self._host, port=self._port)


app = Application(Config.load()).create_app()

if __name__ == "__main__":
    Server("run:app", Config.DEFAULT_HOST, Config.DEFAULT_PORT).start()
