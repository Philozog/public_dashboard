"""Start the dashboard on this computer and open it in the browser.

The start-windows.bat / start-mac.command / start-linux.sh launchers call this.
Set DASH_DEBUG=1 for the Dash developer tools and auto-reload.
"""

import os
import threading
import webbrowser

from app import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8050"))
    debug = os.environ.get("DASH_DEBUG") == "1"
    url = f"http://127.0.0.1:{port}"
    # The debug reloader runs this file twice; open the browser only once.
    if not debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    print(f"\n  AP Terminal is running at {url}\n  Close this window to stop it.\n")
    app.run(host="127.0.0.1", port=port, debug=debug)
