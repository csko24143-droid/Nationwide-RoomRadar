#!/usr/bin/env python3
"""ローカル起動用エントリポイント.

    pip install -r requirements.txt
    python run.py            # http://localhost:10000

``PORT`` 環境変数でポートを変更できる（既定 10000）。
"""

import os

from roomradar.webapp import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port, debug=bool(os.environ.get("DEBUG")))
