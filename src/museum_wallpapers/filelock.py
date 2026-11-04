"""Exclusive file locks that work across processes and threads (flock).

Each call opens its own handle, so two threads of one process exclude each
other just like two processes do: flock locks belong to the open file
description, not to the process.
"""

import fcntl
import time
from pathlib import Path

POLL = 0.1


class FileLock:
    def __init__(self, handle):
        self._handle = handle

    def close(self):
        handle, self._handle = self._handle, None
        if handle is not None:
            handle.close()  # closing the description releases the lock

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()

    def __del__(self):
        self.close()


def _try_lock(handle):
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except (BlockingIOError, PermissionError):
        return False


def acquire(path, wait=True, timeout=None):
    """Lock `path` exclusively; returns a FileLock (a context manager), or
    None when wait=False (or the timeout passed) and another holder has it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a+b")
    deadline = None if timeout is None else time.monotonic() + timeout
    while not _try_lock(handle):
        if not wait or (deadline is not None and time.monotonic() >= deadline):
            handle.close()
            return None
        time.sleep(POLL)
    return FileLock(handle)
