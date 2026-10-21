"""Local macOS/POSIX workspace ownership around the real ReMe file store.

All CJ experiment entrypoints use this owner. Native unwrapped ReMe remains an
explicit counterexample, not a supported writer. flock is advisory, not auth or
a sandbox against same-user code that deliberately ignores the entrypoint.
"""

from contextlib import asynccontextmanager
import asyncio
import fcntl
import os
from pathlib import Path
import stat


class WriterBusy(RuntimeError):
    pass


class WriterClosed(RuntimeError):
    pass


class WorkspaceWriter:
    def __init__(self, workspace, fd, store):
        self.workspace = workspace
        self._fd = fd
        self._store = store
        self._pid = os.getpid()
        self._closed = False
        self._operation_lock = asyncio.Lock()
        self._operation_owner = None

    @classmethod
    async def open(cls):
        workspace = Path.cwd().resolve()
        # Never unlink this file: changing its inode would split the lock domain.
        path = workspace / ".cj003-writer.lock"
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise WriterClosed("writer lock must be one regular file")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise WriterBusy("workspace already has a writer") from error
            # Construct/start only after exclusive ownership, including startup IO.
            from reme.components.file_store import LocalFileStore
            store = LocalFileStore(name="cj003", embedding_store="")
            writer = cls(workspace, fd, store)
            async with writer.operation():
                await store.start()
            return writer
        except BaseException:
            os.close(fd)
            raise

    def require_active(self):
        if self._closed or os.getpid() != self._pid:
            raise WriterClosed("writer is closed or belongs to a different process")
        if Path.cwd().resolve() != self.workspace:
            raise WriterClosed("workspace cwd changed while writer was active")
        held = os.fstat(self._fd)
        current = (self.workspace / ".cj003-writer.lock").lstat()
        if not stat.S_ISREG(current.st_mode) or (held.st_dev, held.st_ino) != (current.st_dev, current.st_ino):
            raise WriterClosed("writer lock identity changed")

    @asynccontextmanager
    async def operation(self):
        task = asyncio.current_task()
        if self._operation_owner is task:
            self.require_active()
            yield
            return
        async with self._operation_lock:
            self.require_active()
            self._operation_owner = task
            try:
                yield
            finally:
                self._operation_owner = None

    async def upsert(self, files):
        async with self.operation():
            return await self._store.upsert(files)

    async def delete(self, path):
        async with self.operation():
            return await self._store.delete(path)

    async def clear(self):
        async with self.operation():
            return await self._store.clear()

    async def dump(self):
        async with self.operation():
            return await self._store.dump()

    async def reindex(self, scope):
        async with self.operation():
            return await self._store.reindex(scope)

    async def optimize_index(self):
        async with self.operation():
            return await self._store.optimize_index()

    async def keyword_search(self, query, limit, search_filter):
        async with self.operation():
            return await self._store.keyword_search(query, limit, search_filter)

    async def close(self):
        async with self._operation_lock:
            if self._closed:
                return
            self.require_active()
            try:
                # ReMe close checkpoints dependencies too; keep flock until done.
                await self._store.close()
            finally:
                self._closed = True
                os.close(self._fd)
