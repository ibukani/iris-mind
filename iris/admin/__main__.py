from __future__ import annotations

import argparse
from pathlib import Path
import secrets
import sys

import yaml

from iris.kernel.config import Config


def _load_config(path: str) -> tuple[Config, dict]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return Config.model_validate(raw), raw


def _save(path: str, config: Config) -> None:
    config.save(path)


def cmd_show(args: argparse.Namespace) -> None:
    config, _ = _load_config(args.config)
    token = config.session.access_token
    if token:
        print(token)
    else:
        print("(not set)")
        sys.exit(1)


def cmd_rotate(args: argparse.Namespace) -> None:
    config, _ = _load_config(args.config)
    old = config.session.access_token
    new = secrets.token_urlsafe(32)
    config.session.access_token = new
    _save(args.config, config)
    if old:
        print(f"Old token: {old}")
    print(f"New token: {new}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Iris Admin CLI")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("show-token", help="Show current access_token")

    sub.add_parser("rotate-token", help="Generate new access_token")

    ns = parser.parse_args()
    if ns.command == "show-token":
        cmd_show(ns)
    elif ns.command == "rotate-token":
        cmd_rotate(ns)


if __name__ == "__main__":
    main()
