"""Offline guards for the advanced-loft live document lifecycle."""

import unittest
from unittest.mock import patch

from tests import native_loft_advanced_live_smoke as smoke


class _Model:
    def __init__(self, title):
        self.title = title

    def GetTitle(self):
        return self.title


class _SolidWorks:
    def __init__(self):
        self.closed = []

    def QuitDoc(self, title):
        self.closed.append(title)


class LiveDocumentLifecycleTests(unittest.TestCase):
    def setUp(self):
        smoke._latest_live_title = None

    def tearDown(self):
        smoke._latest_live_title = None

    def test_new_case_closes_previous_and_never_calls_save(self):
        sw = _SolidWorks()
        models = iter((_Model("Part-A"), _Model("Part-B")))
        with patch.object(smoke, "new_document", side_effect=lambda *_: next(models)):
            _, first = smoke.new_live_part(sw, "first")
            _, second = smoke.new_live_part(sw, "second")

        self.assertEqual(first, "Part-A")
        self.assertEqual(second, "Part-B")
        self.assertEqual(sw.closed, ["Part-A"])
        self.assertEqual(smoke._latest_live_title, "Part-B")

    def test_failed_case_is_discarded(self):
        sw = _SolidWorks()
        with patch.object(smoke, "new_document", return_value=_Model("Part-Failed")):
            _, title = smoke.new_live_part(sw, "failed")
        smoke.discard_live_part(sw, title)

        self.assertEqual(sw.closed, ["Part-Failed"])
        self.assertIsNone(smoke._latest_live_title)


if __name__ == "__main__":
    unittest.main()
