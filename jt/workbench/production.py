"""Environment-only workbench commands for the private Caddy upstream."""

import argparse
import fcntl
import os
import re
import signal
import socket
import stat
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
import uvicorn

from jt.synthetic import generate_dataset

from .__main__ import bootstrap_admin
from .app import HEALTH_HOST, ProxyEntry, create_app
from .auth import AccessDenied, Auth, InvalidAccount
from .postgres import DATABASE_VARIABLE, PostgresStore, migrate


HOST_VARIABLE = "JT_WORKBENCH_PUBLIC_HOST"
SOCKET_VARIABLE = "JT_WORKBENCH_HTTP_SOCKET"
HOSTNAME = re.compile(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
SOCKET_MODE = 0o660


def socket_path() -> Path:
    path = Path(os.environ.get(SOCKET_VARIABLE, ""))
    if not path.is_absolute() or path.name != "http.sock":
        raise RuntimeError("invalid workbench socket path")
    return path


@contextmanager
def private_listener(path: Path) -> Iterator[socket.socket]:
    directory = path.parent.lstat()
    if (not stat.S_ISDIR(directory.st_mode) or directory.st_uid != os.geteuid()
            or directory.st_mode & 0o027):
        raise RuntimeError("workbench socket directory must be private and owned by the runtime user")
    lock_fd = os.open(path.parent / "http.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock_fd, "rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            old = path.lstat()
        except FileNotFoundError:
            pass
        else:
            if not stat.S_ISSOCK(old.st_mode) or old.st_uid != os.geteuid():
                raise RuntimeError("workbench socket path is already occupied")
            path.unlink()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.bind(str(path))
            try:
                path.chmod(SOCKET_MODE)
                listener.listen()
                yield listener
            finally:
                path.unlink()


def probe_health(path: Path) -> bool:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(3)
        client.connect(str(path))
        client.sendall(f"GET /healthz HTTP/1.1\r\nHost: {HEALTH_HOST}\r\nConnection: close\r\n\r\n".encode())
        with client.makefile("rb") as response:
            return response.readline(256).startswith(b"HTTP/1.1 200 ")


def serve_workbench(store: PostgresStore, auth: Auth) -> None:
    host = os.environ.get(HOST_VARIABLE, "")
    if not HOSTNAME.fullmatch(host):
        raise RuntimeError("invalid workbench public hostname")
    path = socket_path()
    store.seed(generate_dataset().signals)
    app = create_app(auth, queue=store, proxy=ProxyEntry(host, store.check_ready))
    config = uvicorn.Config(app, proxy_headers=False, access_log=False, server_header=False)
    with private_listener(path) as listener:
        server = uvicorn.Server(config)
        previous = signal.signal(signal.SIGTERM, server.handle_exit)
        try:
            server.run(sockets=[listener])
        finally:
            signal.signal(signal.SIGTERM, previous)
        if not server.started:
            raise RuntimeError("workbench server did not start")


def main() -> None:
    parser = argparse.ArgumentParser(description="JT 工作台容器入口")
    parser.add_argument("command", choices=("migrate", "bootstrap-admin", "bootstrap-admin-code", "serve", "healthcheck"))
    parser.add_argument("--username", help="只用于签发首个管理员设置码")
    args = parser.parse_args()
    command = args.command
    if (command == "bootstrap-admin-code") != (args.username is not None):
        parser.error("bootstrap-admin-code 必须提供 --username。")
    if command == "bootstrap-admin-code" and not sys.stdout.isatty():
        parser.error("请在私有交互式终端签发设置码。")
    try:
        if command == "healthcheck":
            if not probe_health(socket_path()):
                parser.exit(1, "工作台健康检查未通过。\n")
            return
        dsn = os.environ.get(DATABASE_VARIABLE)
        if not dsn:
            parser.error(f"缺少 {DATABASE_VARIABLE}。")
        if command == "migrate":
            migrate(dsn)
            return
        store = PostgresStore(dsn)
        store.check_ready()
        auth = Auth(store, clock=store.clock, monotonic=store.clock)
        if command == "bootstrap-admin":
            with store.locked():
                already_configured = bool(store.accounts())
            if already_configured:
                parser.error("工作台管理员已经引导。")
            bootstrap_admin(auth, parser)
        elif command == "bootstrap-admin-code":
            code = auth.issue_initial_admin_setup(args.username)
            print("请私下交给账号本人。在登录页选择首次设置，设置码有效 15 分钟。")
            print(code)
        else:
            serve_workbench(store, auth)
    except (AccessDenied, InvalidAccount, OSError, RuntimeError, psycopg.Error):
        parser.exit(1, f"工作台 {command} 未完成。请核对运行配置和数据库权限。\n")


if __name__ == "__main__":
    main()
