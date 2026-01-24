import unittest

from app.services.network_resource_service import network_resource_service


class TestResourcesWsPayload(unittest.TestCase):
    def test_payload_filters_none_values(self):
        payload = network_resource_service._build_ws_resources_payload(
            1,
            ["interfaces", "routes"],
            {"interfaces": [{"name": "eth0"}], "routes": None},
        )
        self.assertEqual(payload.get("type"), "resources_updated")
        self.assertEqual(payload.get("device_id"), 1)
        self.assertEqual(payload.get("resources"), ["interfaces", "routes"])
        data = payload.get("data")
        self.assertIsInstance(data, dict)
        self.assertIn("interfaces", data)
        self.assertNotIn("routes", data)

