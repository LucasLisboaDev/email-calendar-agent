"""
start.py

Launches the FastAPI server and ngrok tunnel together in one command.

Why ngrok?
- Your FastAPI runs on localhost — nothing outside your machine can reach it
- ngrok creates a public HTTPS URL that tunnels to your local port
- This lets n8n webhooks, external testers, and Railway health checks
  reach your agent during development without deploying

Usage:
    python start.py

What happens:
    1. FastAPI starts on localhost:8000
    2. ngrok opens a tunnel and prints the public URL
    3. The public URL is printed — share it or use it in n8n

Requirements:
    - ngrok installed: brew install ngrok (or download from ngrok.com)
    - ngrok auth token set: ngrok config add-authtoken <your-token>
    - Or set NGROK_AUTHTOKEN in your .env file
"""

import os
import sys
import subprocess
import threading
import time
import signal
from dotenv import load_dotenv

load_dotenv()

PORT = int(os.getenv("PORT", 8000))
NGROK_TOKEN = os.getenv("NGROK_AUTHTOKEN", "")


def start_fastapi():
    """Start the uvicorn server."""
    subprocess.run(
        [
            sys.executable, "-m", "uvicorn",
            "api.app:app",
            "--host", "0.0.0.0",
            "--port", str(PORT),
            "--reload",
        ],
        check=True,
    )


def start_ngrok():
    """Start ngrok tunnel and print the public URL."""
    # Give uvicorn 2 seconds to start before opening the tunnel
    time.sleep(2)

    if NGROK_TOKEN:
        os.system(f"ngrok config add-authtoken {NGROK_TOKEN} --log=false 2>/dev/null")

    print("\n" + "=" * 60)
    print("Starting ngrok tunnel...")
    print("=" * 60)

    try:
        # Start ngrok and capture the public URL via the API
        ngrok_process = subprocess.Popen(
            ["ngrok", "http", str(PORT), "--log=stdout"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Wait for ngrok to print the URL
        time.sleep(3)

        # Fetch the URL from ngrok's local API
        import urllib.request
        import json

        try:
            with urllib.request.urlopen("http://localhost:4040/api/tunnels") as response:
                data = json.loads(response.read())
                tunnels = data.get("tunnels", [])
                if tunnels:
                    public_url = tunnels[0]["public_url"]
                    # Prefer HTTPS
                    for t in tunnels:
                        if t["public_url"].startswith("https"):
                            public_url = t["public_url"]
                            break

                    print("\n" + "🚀 " * 20)
                    print(f"\n  PUBLIC URL: {public_url}")
                    print(f"\n  API docs:   {public_url}/docs")
                    print(f"  Health:     {public_url}/health")
                    print(f"  Run agent:  POST {public_url}/run")
                    print(f"  Pending:    GET  {public_url}/pending")
                    print("\n" + "🚀 " * 20 + "\n")
        except Exception:
            print("\nngrok is running. Check http://localhost:4040 for the public URL.")

        ngrok_process.wait()

    except FileNotFoundError:
        print("\n⚠️  ngrok not found.")
        print("Install it: brew install ngrok")
        print("Then set your auth token: ngrok config add-authtoken <token>")
        print(f"\nFastAPI is still running at http://localhost:{PORT}")
        print(f"Docs: http://localhost:{PORT}/docs\n")


def main():
    print("\n" + "=" * 60)
    print("Email & Calendar Automation Agent — Phase 3")
    print("=" * 60)
    print(f"Starting FastAPI on port {PORT}...")

    # Run FastAPI in a background thread, ngrok in another
    fastapi_thread = threading.Thread(target=start_fastapi, daemon=True)
    fastapi_thread.start()

    # ngrok runs in the main thread so its output is visible
    try:
        start_ngrok()
    except KeyboardInterrupt:
        print("\nShutting down...")
        sys.exit(0)


if __name__ == "__main__":
    main()
