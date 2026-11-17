"""离线读出发布包唯一的 alembic head，供发布脚本断言使用。

**不要**在 `ops/` 里写死 head 常量：每加一个迁移都要手改一遍，忘了就会把一次
正确的部署判成失败（v1.13.1 P1-4）。这里只解析 `alembic/versions/*.py` 的
`revision` / `down_revision`，不依赖 alembic 包，宿主机 `python3` 就能跑。

用法：`python3 -B ops/expected_head.py [发布包根目录]`，只打印 head 字符串。
"""
import re
import sys
from pathlib import Path

REVISION = re.compile(r"^revision\s*=\s*['\"]([^'\"]+)['\"]", re.M)
DOWN_REVISION = re.compile(r"^down_revision\s*=\s*(?:['\"]([^'\"]+)['\"]|None)", re.M)


def revisions(root):
    """{revision: 文件名}。重复 revision 直接报错，不猜。"""
    found = {}
    for path in sorted((Path(root) / 'alembic' / 'versions').glob('*.py')):
        text = path.read_text(encoding='utf-8')
        match = REVISION.search(text)
        if not match:
            raise ValueError('REVISION_MISSING:' + path.name)
        revision = match.group(1)
        if revision in found:
            raise ValueError('DUPLICATE_REVISION:' + revision)
        found[revision] = path.name
    if not found:
        raise ValueError('NO_REVISION_FILES')
    return found


def known_revisions(root):
    """本发布包认识的全部 revision（用于判断库里的 head 是不是本包能接管的旧版本）。"""
    return set(revisions(root))


def head(root):
    """本发布包唯一的 head。多个 head 说明有未合并分支，发布前必须解决。"""
    graph = revisions(root)
    children = set()
    for path in sorted((Path(root) / 'alembic' / 'versions').glob('*.py')):
        match = DOWN_REVISION.search(path.read_text(encoding='utf-8'))
        if match and match.group(1):
            children.add(match.group(1))
    unknown = sorted(children - set(graph))
    if unknown:
        raise ValueError('UNKNOWN_DOWN_REVISION:' + unknown[0])
    heads = sorted(set(graph) - children)
    if len(heads) != 1:
        raise ValueError('MULTIPLE_HEADS' if heads else 'NO_HEAD')
    return heads[0]


if __name__ == '__main__':
    print(head(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]))
