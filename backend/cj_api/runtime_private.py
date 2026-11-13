"""Owned-file and owned-directory checks at the runtime filesystem trust boundary."""
from contextlib import contextmanager
import os
import stat


class PrivateFileError(ValueError):
    def __init__(self,reason):
        self.reason=reason
        super().__init__('private runtime file unavailable')


def read_private(path,limit,*,directory_fd=None):
    descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory_fd)
    with os.fdopen(descriptor,'rb') as source:
        info=os.fstat(source.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid()
                or stat.S_IMODE(info.st_mode)!=0o600):
            raise PrivateFileError('authority')
        raw=source.read(limit+1)
    if len(raw)>limit:raise PrivateFileError('bound')
    return raw


@contextmanager
def private_directory(path,failure):
    """Open an owner-only (0700) directory without following links, else raise failure."""
    descriptor=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        info=os.fstat(descriptor)
        if info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:
            raise failure
        yield descriptor
    finally:os.close(descriptor)
