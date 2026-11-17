"""Process-coordinated local workloads; no daemon and no model downloads."""
from contextlib import contextmanager
import fcntl
import gc
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import time

_LOCK = threading.RLock()


class ResourceUnavailable(RuntimeError):
    pass


def memory_status():
    if __import__('sys').platform == 'darwin':
        try:
            output = subprocess.run(['/usr/bin/memory_pressure', '-Q'], capture_output=True, text=True, timeout=3, check=True).stdout
            match = re.search(r'memory free percentage:\s*(\d+)%', output)
            return {'free_percent': int(match[1]) if match else None}
        except (OSError, subprocess.SubprocessError):
            return {'free_percent': None}
    try:
        fields = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
        return {'free_percent': int(100 * int(fields['MemAvailable'].split()[0]) / int(fields['MemTotal'].split()[0]))}
    except (OSError, KeyError, ValueError):
        return {'free_percent': None}


@contextmanager
def workload(*, timeout=10.0, lock_path=None):
    """Advisory flock auto-releases after crashes; never delete a live lock inode.

    Unknown pressure fails closed. Kernel lock ownership, rather than PID-file
    expiry, provides stale-owner recovery. Only cooperating Oracle processes obey it.
    """
    if not 0 < timeout <= 60:
        raise ValueError('timeout must be in (0, 60]')
    path = lock_path or os.path.join(tempfile.gettempdir(), f'oracle-local-model-{os.getuid()}.lock')
    started = time.monotonic()
    if not _LOCK.acquire(timeout=timeout):
        raise ResourceUnavailable('local_model_thread_lock_timeout')
    try:
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() - started >= timeout:
                        raise ResourceUnavailable('local_model_lock_timeout')
                    time.sleep(0.05)
            before = memory_status()
            if before['free_percent'] is None or before['free_percent'] < 15:
                raise ResourceUnavailable('memory_pressure_or_unavailable')
            state = {'before': before}
            try:
                yield state
            finally:
                gc.collect()
                state['after'] = memory_status()
        finally:
            os.close(fd)
    finally:
        _LOCK.release()
