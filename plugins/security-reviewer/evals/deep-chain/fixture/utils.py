"""Unrelated helpers.

TEST FIXTURE ONLY (see README.md).
"""

import hashlib
import subprocess


def thumbnail_cache_key(path):
    # MD5 only names a cache file. It is not a security control and guards nothing.
    return hashlib.md5(path.encode("utf-8")).hexdigest()


def make_thumbnail(src_path, dst_path):
    # Fixed binary, argument list form (no shell), and both paths are
    # server-chosen temp files, never request strings.
    subprocess.run(
        ["/usr/bin/convert", src_path, "-resize", "64x64", dst_path], check=True
    )
