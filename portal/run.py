import threading
import webbrowser

from waitress import serve
from app import app

HOST = "127.0.0.1"
PORT = 5050


def _open_browser():
    webbrowser.open(f"http://{HOST}:{PORT}/")


if __name__ == "__main__":
    threading.Timer(1.0, _open_browser).start()
    serve(app, host=HOST, port=PORT)
