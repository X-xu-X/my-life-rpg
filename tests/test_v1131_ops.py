"""v1.13.1 批次 G：发布链断言不再写死 head。

`ops/` 里一旦把 head 写成常量，下一次加迁移就会把正确部署判成失败。
这里锁住两件事：解析器能从本仓库算出唯一的 head；多分支时报错而不是随便挑一个。
"""
import tempfile
import unittest
from pathlib import Path

from ops.expected_head import head, known_revisions

ROOT = Path(__file__).resolve().parents[1]


def write(root, name, revision, down_revision):
    versions = Path(root) / 'alembic' / 'versions'
    versions.mkdir(parents=True, exist_ok=True)
    down = 'None' if down_revision is None else repr(down_revision)
    (versions / name).write_text(f"revision = {revision!r}\ndown_revision = {down}\n", encoding='utf-8')


class ExpectedHeadTests(unittest.TestCase):
    def test_repository_has_exactly_one_head(self):
        self.assertEqual(head(ROOT), 'b027_suppressed_lines')

    def test_known_revisions_cover_the_chain(self):
        revisions = known_revisions(ROOT)
        self.assertIn('b025_daily_use', revisions)
        self.assertIn('b027_suppressed_lines', revisions)

    def test_multiple_heads_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, 'a.py', 'a', None)
            write(root, 'b.py', 'b', 'a')
            write(root, 'c.py', 'c', 'a')
            with self.assertRaisesRegex(ValueError, 'MULTIPLE_HEADS'):
                head(root)

    def test_unknown_parent_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, 'a.py', 'a', 'missing')
            with self.assertRaisesRegex(ValueError, 'UNKNOWN_DOWN_REVISION'):
                head(root)

    def test_double_and_single_quotes_both_parse(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, 'a.py', 'a', None)
            (Path(root) / 'alembic' / 'versions' / 'b.py').write_text(
                'revision="b"\ndown_revision = "a"\n', encoding='utf-8')
            self.assertEqual(head(root), 'b')


if __name__ == '__main__':
    unittest.main()
