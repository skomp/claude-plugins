"""Unrelated helpers.

TEST FIXTURE ONLY (see README.md).
"""

import hashlib
import subprocess


def thumbnail_cache_key(path):
    # Name for the cached thumbnail of a given source path.
    return hashlib.md5(path.encode("utf-8")).hexdigest()


def make_thumbnail(src_path, dst_path):
    subprocess.run(
        ["/usr/bin/convert", src_path, "-resize", "64x64", dst_path], check=True
    )
