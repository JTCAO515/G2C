"""Serve an isolated JT drill on loopback TLS and emit the audit-based report on exit."""

import argparse
import asyncio
import json
import math
import sys
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path

import uvicorn

from jt.workbench.__main__ import bootstrap_admin
from jt.workbench.app import create_app
from jt.workbench.auth import Auth
from jt.workbench.store import MemoryStore

from .report import make_report
from .runner import Drill, prepare_arrivals


def main() -> int:
    parser = argparse.ArgumentParser(description="在本机回环 TLS 工作台运行一批合成演练。")
    parser.add_argument("--cert", type=Path, required=True, help="本地回环 TLS 证书")
    parser.add_argument("--key", type=Path, required=True, help="本地回环 TLS 私钥")
    parser.add_argument("--port", type=int, default=8443)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--minutes", type=float, default=30)
    parser.add_argument("--p0", type=int, default=1)
    parser.add_argument("--start-delay", type=float, default=180, help="启动后第一单前的准备秒数")
    parser.add_argument("--report", type=Path, help="新建本地 JSON 报告文件，省略时写入标准输出")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535 or not args.cert.is_file() or not args.key.is_file():
        parser.error("请提供有效的端口（1024 至 65535）和本地 TLS 文件。")
    if not math.isfinite(args.start_delay) or args.start_delay < 0:
        parser.error("准备秒数必须有限且不小于 0。")
    store = MemoryStore()
    auth = Auth(store)
    bootstrap_admin(auth, parser)
    try:
        arrivals = asyncio.run(prepare_arrivals(
            args.count, args.minutes, args.p0,
            starts_at=datetime.now(UTC) + timedelta(seconds=args.start_delay),
        ))
    except (ValueError, OverflowError) as exc:
        parser.error(str(exc))

    drill = Drill(arrivals, store)
    app = create_app(auth, port=args.port, queue=drill.queue, cases=drill.workspace)
    server = uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=args.port, ssl_certfile=str(args.cert), ssl_keyfile=str(args.key),
        proxy_headers=False, access_log=False,
    ))
    original_lifespan = app.router.lifespan_context
    errors: list[BaseException] = []

    async def drive():
        release = asyncio.create_task(drill.release(args.start_delay))
        try:
            while True:
                if release.done():
                    release.result()
                drill.respond_to_synthetic_consent_requests()
                await asyncio.sleep(0.25)
        finally:
            release.cancel()
            with suppress(asyncio.CancelledError):
                await release

    def stop_on_failure(task):
        if not task.cancelled() and task.exception() is not None:
            errors.append(task.exception())
            server.should_exit = True

    @asynccontextmanager
    async def lifespan(application):
        async with original_lifespan(application):
            task = asyncio.create_task(drive())
            task.add_done_callback(stop_on_failure)
            try:
                yield
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    app.router.lifespan_context = lifespan
    report_file = None
    if args.report is not None:
        try:
            report_file = args.report.open("x", encoding="utf-8")
        except OSError as exc:
            parser.error(str(exc))
    try:
        print(
            f"本地演练 https://127.0.0.1:{args.port}/login，"
            f"{args.start_delay:g} 秒后开始注入。按 Ctrl-C 输出报告。",
            file=sys.stderr, flush=True,
        )
        with suppress(KeyboardInterrupt):
            server.run()
    finally:
        report = make_report(drill)
        encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if report_file is None:
            print(encoded, end="", flush=True)
        else:
            with report_file:
                report_file.write(encoded)
    if errors:
        raise errors[0]
    return 0 if report["status"] == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
