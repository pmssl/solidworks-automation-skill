"""SolidWorks 文档保存的无人值守安全门禁测试。"""

import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_connect


class _Extension:
    def __init__(self):
        self.calls = []

    def SaveAs(self, *args):
        self.calls.append(args)
        return True


class _Model:
    def __init__(self, path=""):
        self.path = path
        self.Extension = _Extension()
        self.save3_calls = []

    def GetPathName(self):
        return self.path

    def Save3(self, *args):
        self.save3_calls.append(args)
        return True


class SaveDocumentSafetyTests(unittest.TestCase):
    def test_blocks_unnamed_document_without_path(self):
        """未命名文档不得调用会打开另存为窗口的 Save3。"""
        model = _Model()

        self.assertFalse(sw_connect.save_document(model))
        self.assertEqual(model.save3_calls, [])
        self.assertEqual(model.Extension.calls, [])

    def test_uses_save3_for_named_document(self):
        """已有原生路径的文档仍可在当前位置静默保存。"""
        model = _Model(r"D:\\parts\\named.SLDPRT")

        self.assertTrue(sw_connect.save_document(model))
        self.assertEqual(len(model.save3_calls), 1)
        self.assertEqual(model.Extension.calls, [])

    def test_uses_save_as_for_explicit_path(self):
        """显式路径继续使用 SaveAs，不受未命名门禁影响。"""
        model = _Model()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "saved.SLDPRT"

            self.assertTrue(sw_connect.save_document(model, target))
            self.assertEqual(model.save3_calls, [])
            self.assertEqual(len(model.Extension.calls), 1)
            self.assertEqual(model.Extension.calls[0][0], str(target.resolve()))


if __name__ == "__main__":
    unittest.main()
