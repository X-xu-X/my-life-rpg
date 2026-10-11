"""Verify a delivered source tree without Git or third-party modules."""
import hashlib
import json
import sys
from pathlib import Path


def verify(path):
    path=Path(path).resolve();root=path.parent;manifest=json.loads(path.read_text())
    for relative,digest in manifest['files'].items():
        target=root/relative
        if target.is_symlink() or not target.resolve().is_relative_to(root) or not target.is_file():raise ValueError('PACKAGE_PATH')
        if hashlib.sha256(target.read_bytes()).hexdigest()!=digest:raise ValueError('PACKAGE_CHECKSUM')
    return {'status':'PASS','release_id':manifest['release_id'],'files':len(manifest['files']),
        'images':manifest['image_status']}


if __name__=='__main__':
    try:print(json.dumps(verify(sys.argv[1])))
    except Exception:print('FAIL: package checksum/path validation');raise SystemExit(2)
