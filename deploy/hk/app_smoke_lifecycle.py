"""Private live capture health, independent of evidence-file write success.

The API instance latches loss in memory before attempting persistence. The
operator pins its fresh instance ID; a restart, unavailable socket, loss or dead
collector invalidates that qualification. This is a deny-only evidence gate,
never a replacement for original AUTH/MESSAGE/Memory or financial authority.
"""
import json
import os
from pathlib import Path
import socket
import stat
import struct
import sys
import threading
from uuid import uuid4

from cj_usage.authorization_budget import canonical
from cj_strict_json import reject_duplicates
from runtime_adapter.contract import Unavailable

VERSION='G2C-App-smoke-live-capture.1'
NAME='capture-status.sock'


def read_status(controls):
    controls.guard()
    with controls.directory()as directory:
        info=os.stat(NAME,dir_fd=directory,follow_symlinks=False)
        if not stat.S_ISSOCK(info.st_mode)or info.st_uid!=os.getuid()or stat.S_IMODE(info.st_mode)!=0o600:
            raise Unavailable('APP_SMOKE_LIVE_SOCKET_AUTHORITY')
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)as connection:
        connection.settimeout(2)
        connection.connect(str(Path(controls.window['directory'])/NAME))
        if sys.platform.startswith('linux'):
            peer=struct.unpack('3i',connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
            if peer[1]!=os.getuid():raise Unavailable('APP_SMOKE_LIVE_PEER_CHANGED')
        data=bytearray()
        while True:
            chunk=connection.recv(4097-len(data))
            if not chunk:break
            data.extend(chunk)
            if len(data)>4096:raise Unavailable('APP_SMOKE_LIVE_STATUS_BOUND')
    value=json.loads(data,object_pairs_hook=reject_duplicates(ValueError,'duplicate live capture field'))
    fields={'version','instance_id','source_commit','policy_sha256','lost','observer_alive'}
    if(type(value)is not dict or set(value)!=fields or value['version']!=VERSION
            or type(value['instance_id'])is not str or len(value['instance_id'])!=32
            or any(c not in'0123456789abcdef'for c in value['instance_id'])
            or value['source_commit']!=controls.policy['source_commit']
            or value['policy_sha256']!=controls.window['policy_sha256']
            or type(value['lost'])is not bool or type(value['observer_alive'])is not bool):
        raise Unavailable('APP_SMOKE_LIVE_STATUS_CHANGED')
    controls.guard()
    return value


def require_live(controls,instance):
    try:value=read_status(controls)
    except (OSError,ValueError):
        raise Unavailable('APP_SMOKE_LIVE_STATUS_UNAVAILABLE')from None
    if(value['instance_id']!=instance or value['lost']or not value['observer_alive']):
        raise Unavailable('APP_SMOKE_CAPTURE_LIFECYCLE_INVALID')
    return value


class CaptureLifecycle:
    def __init__(self,controls,lost,observer_alive):
        self.controls,self.lost,self.observer_alive=controls,lost,observer_alive
        self.instance_id=uuid4().hex;self.closed=threading.Event()
        self.path=Path(controls.window['directory'])/NAME
        self.server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        try:
            with controls.directory()as directory:
                try:old=os.stat(NAME,dir_fd=directory,follow_symlinks=False)
                except FileNotFoundError:old=None
                if old is not None:
                    if not stat.S_ISSOCK(old.st_mode)or old.st_uid!=os.getuid():
                        raise Unavailable('APP_SMOKE_OLD_SOCKET_AUTHORITY')
                    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)as probe:
                        probe.settimeout(.2)
                        try:probe.connect(str(self.path))
                        except ConnectionRefusedError:os.unlink(NAME,dir_fd=directory)
                        else:raise Unavailable('APP_SMOKE_CAPTURE_INSTANCE_ALREADY_ACTIVE')
                self.server.bind(str(self.path));os.chmod(self.path,0o600)
            self.server.listen(4);self.server.settimeout(.1)
            self.thread=threading.Thread(target=self._serve,name='app-smoke-live-status',daemon=True)
            self.thread.start()
        except BaseException:
            self.server.close();raise

    def _serve(self):
        while not self.closed.is_set():
            try:connection,_=self.server.accept()
            except socket.timeout:continue
            except OSError:
                if self.closed.is_set():return
                self.lost.set();return
            with connection:
                connection.settimeout(2)
                value=dict(version=VERSION,instance_id=self.instance_id,
                    source_commit=self.controls.policy['source_commit'],policy_sha256=self.controls.window['policy_sha256'],
                    lost=self.lost.is_set(),observer_alive=self.observer_alive())
                try:connection.sendall(canonical(value))
                except OSError:self.lost.set()

    def close(self):
        self.closed.set();self.server.close();self.thread.join(timeout=1)
