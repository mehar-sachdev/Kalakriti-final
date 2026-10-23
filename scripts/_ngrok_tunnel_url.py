#!/usr/bin/env python
"""Read ngrok's local API (http://127.0.0.1:4040/api/tunnels) and print the
public https URL. Kept as its own file (rather than an inline snippet in
start_ngrok.sh) so the JSON parsing doesn't fight with bash quoting.

    python scripts/_ngrok_tunnel_url.py

Prints nothing and exits non-zero if ngrok hasn't opened a tunnel yet.
"""
import json
import sys
import urllib.error
import urllib.request


def main() -> int:
    try:
        with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=2) as resp:
            data = json.load(resp)
    except (urllib.error.URLError, OSError, ValueError):
        return 1

    for tunnel in data.get("tunnels", []):
        if tunnel.get("proto") == "https":
            print(tunnel["public_url"])
            return 0
    # Fall back to any tunnel (e.g. http-only) if no https one is listed yet.
    for tunnel in data.get("tunnels", []):
        if tunnel.get("public_url"):
            print(tunnel["public_url"])
            return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
