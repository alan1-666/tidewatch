import unittest

import tidewatch


class PackageTest(unittest.TestCase):
    # 占位冒烟用例：保证验证 profile 真的发现并运行了测试，第一个业务任务落地后可删除。
    def test_importable(self):
        self.assertRegex(tidewatch.__version__, r'^\d+\.\d+\.\d+$')


if __name__ == '__main__':
    unittest.main()
