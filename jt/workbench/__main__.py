"""Prompt for a synthetic bootstrap administrator and serve only on loopback TLS."""

import argparse
import sys
import warnings
from getpass import GetPassWarning, getpass
from pathlib import Path

import uvicorn

from .app import create_app
from .auth import Auth, InvalidAccount
from .store import MemoryStore


def main() -> None:
    parser = argparse.ArgumentParser(description="在本机回环地址启动 JT 工作台（仅合成数据）")
    parser.add_argument("--cert", type=Path, required=True, help="本地 TLS 证书文件")
    parser.add_argument("--key", type=Path, required=True, help="本地 TLS 私钥文件")
    parser.add_argument("--port", type=int, default=8443)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535 or not args.cert.is_file() or not args.key.is_file():
        parser.error("请提供有效的端口（1024 至 65535）和本地 TLS 文件。")

    if not sys.stdin.isatty():
        parser.error("请在交互式终端中创建本地管理员。")
    auth = Auth(MemoryStore())
    username = input("管理员账号：").strip()
    with warnings.catch_warnings():
        warnings.simplefilter("error", GetPassWarning)
        try:
            password = getpass("管理员密码：")
            seed = getpass("验证器的 Base32 密钥：")
            code = getpass("绑定用的当前动态验证码：")
        except GetPassWarning:
            parser.error("终端无法隐藏输入。")
    try:
        auth.bootstrap_admin(username, password, seed, code)
    except InvalidAccount:
        parser.error("无法创建管理员。请核对账号、密码及验证器设置。")
    del password, seed, code
    print(f"登录：https://127.0.0.1:{args.port}/login （使用验证器下一组验证码）", flush=True)
    uvicorn.run(create_app(auth, port=args.port), host="127.0.0.1", port=args.port,
                ssl_certfile=str(args.cert), ssl_keyfile=str(args.key), proxy_headers=False, access_log=False)


if __name__ == "__main__":
    main()
