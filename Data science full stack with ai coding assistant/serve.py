"""Launch every app:  python serve.py   ->  http://127.0.0.1:8000"""
import argparse

import uvicorn

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    uvicorn.run("shared.hub:app", host=args.host, port=args.port)
