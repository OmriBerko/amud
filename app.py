"""Run Amud locally: python app.py"""

import os

from amud import create_app

app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="127.0.0.1", port=port, debug=False)
