"""
Start the Stock Analysis Tool as a web server.

Usage:
    python start_server.py runserver [--host HOST] [--port PORT]
"""

from __future__ import annotations
import argparse
import sys

import flet as ft

from main import main as app_main


def runserver(host: str, port: int) -> None:
    ft.run(app_main, view=ft.AppView.WEB_BROWSER, host=host, port=port)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stock Analysis Tool server")
    subparsers = parser.add_subparsers(dest="command", required=True)

    runserver_parser = subparsers.add_parser("runserver", help="Start the web server")
    runserver_parser.add_argument("--host", default="127.0.0.1")
    runserver_parser.add_argument("--port", type=int, default=8550)

    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "runserver":
        runserver(args.host, args.port)


if __name__ == "__main__":
    main(sys.argv[1:])
