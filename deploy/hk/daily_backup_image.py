"""Read the root-owned local image selection for the existing backup timer."""
import os
import re
import stat
import sys


def read_selection(path):
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    with os.fdopen(descriptor, 'rb') as source:
        info = os.fstat(source.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
                or info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)):
            raise ValueError('root-owned backup image selection required')
        record = source.read(256)
    selection = re.fullmatch(rb'(g2c-beta-operator:[0-9a-f]{40}) (sha256:[0-9a-f]{64})\n?', record)
    if selection is None:
        raise ValueError('fixed backup source and local image ID required')
    return selection[1].decode('ascii'), selection[2].decode('ascii')


if __name__ == '__main__':
    try:
        selected = read_selection('backup.image')
    except (OSError, ValueError):
        print('ALERT beta_backup_image_selection_invalid', file=sys.stderr)
        raise SystemExit(1) from None
    if selected is not None:
        print(*selected)
