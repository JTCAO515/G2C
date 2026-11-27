"""Prompt for a local bootstrap administrator and serve only on loopback TLS."""

import argparse
import sys
import warnings
from os import environ
from getpass import GetPassWarning, getpass
from pathlib import Path

import psycopg
import uvicorn

from jt.synthetic import generate_dataset

from .app import create_app
from .auth import AccessDenied, Auth, InvalidAccount
from .postgres import DATABASE_VARIABLE, PostgresStore
from .store import MemoryStore


def main() -> None:
    parser = argparse.ArgumentParser(description="在本机回环地址启动 JT 工作台（仅合成数据）")
    parser.add_argument("--cert", type=Path, required=True, help="本地 TLS 证书文件")
    parser.add_argument("--key", type=Path, required=True, help="本地 TLS 私钥文件")
    parser.add_argument("--port", type=int, default=8443)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535 or not args.cert.is_file() or not args.key.is_file():
        parser.error("请提供有效的端口（1024 至 65535）和本地 TLS 文件。")

    queue = None
    if DATABASE_VARIABLE in environ:
        queue = PostgresStore(environ[DATABASE_VARIABLE])
        try:
            queue.check_ready()
            queue.seed(generate_dataset().signals)
        except (psycopg.Error, RuntimeError):
            parser.error("工作台数据库未就绪或权限不符合要求。")
        auth = Auth(queue, clock=queue.clock, monotonic=queue.clock)
    else:
        auth = Auth(MemoryStore())
    if not auth.has_admin():
        bootstrap_admin(auth, parser)
    print(f"登录：https://127.0.0.1:{args.port}/login", flush=True)
    uvicorn.run(create_app(auth, port=args.port, queue=queue), host="127.0.0.1", port=args.port,
                ssl_certfile=str(args.cert), ssl_keyfile=str(args.key), proxy_headers=False, access_log=False)


def bootstrap_admin(auth: Auth, parser: argparse.ArgumentParser, username: str | None = None) -> None:
    """Create the first administrator. The password is read without echo and is never printed or logged."""
    if not sys.stdin.isatty():
        parser.error("请在交互式终端中创建管理员。")
    if username is None:
        username = input("管理员账号：").strip()
    with warnings.catch_warnings():
        warnings.simplefilter("error", GetPassWarning)
        try:
            password = getpass("管理员密码（至少 12 位）：")
            confirm = getpass("再次输入密码：")
        except GetPassWarning:
            parser.error("终端无法隐藏输入。")
    if password != confirm:
        parser.error("两次输入的密码不一致。")
    try:
        auth.bootstrap_admin(username, password)
    except AccessDenied:
        parser.error("工作台已有管理员，拒绝执行。")
    except InvalidAccount:
        parser.error("无法创建管理员。请核对账号（3 至 32 位小写字母、数字、下划线、连字符）和密码长度（至少 12 位）。")
    finally:
        del password, confirm
    print(f"管理员 {username} 已创建。", flush=True)


if __name__ == "__main__":
    main()
