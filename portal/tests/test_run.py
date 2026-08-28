import runpy
from unittest.mock import patch


def test_run_starts_server_and_opens_browser():
    with patch("waitress.serve") as mock_serve, patch("webbrowser.open") as mock_open, \
         patch("threading.Timer") as mock_timer:
        runpy.run_module("run", run_name="__main__")

        mock_timer.assert_called_once()
        args, _ = mock_timer.call_args
        assert args[0] == 1.0

        callback = args[1]
        callback()
        mock_open.assert_called_once_with("http://127.0.0.1:5050/")

        mock_serve.assert_called_once()
