import json
import unittest

from app.utils.pg_json import jsonb_param


class TestJsonbParam(unittest.TestCase):
    def test_list_encoded(self) -> None:
        payload = jsonb_param(["sys:monitor:view"])
        self.assertIsInstance(payload, str)
        self.assertEqual(json.loads(payload), ["sys:monitor:view"])

    def test_str_passthrough(self) -> None:
        payload = jsonb_param('["sys:monitor:view"]')
        self.assertEqual(payload, '["sys:monitor:view"]')

    def test_none(self) -> None:
        self.assertIsNone(jsonb_param(None))
