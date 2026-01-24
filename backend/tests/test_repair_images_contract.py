import unittest


class TestRepairImagesContract(unittest.TestCase):
    def test_system_config_meta_exposes_remote_image_configs(self):
        from app.api.v1.endpoints import system

        self.assertIn("repair_image_api_base_url", system._DEFAULT_CONFIG_META)
        self.assertIn("repair_image_api_email", system._DEFAULT_CONFIG_META)
        self.assertIn("repair_image_api_password", system._DEFAULT_CONFIG_META)
        self.assertNotIn("repair_image_upload_base_url", system._DEFAULT_CONFIG_META)
        self.assertNotIn("repair_image_storage_provider", system._DEFAULT_CONFIG_META)
        self.assertNotIn("repair_image_api_token", system._DEFAULT_CONFIG_META)
        self.assertNotIn("repair_image_api_strategy_id", system._DEFAULT_CONFIG_META)

    def test_rbac_has_repair_image_permissions(self):
        from app.services.rbac_service import RbacService

        codes = {p.get("code") for p in (RbacService.SYSTEM_PERMISSIONS or [])}
        expected = {
            "sys:repair:image:view",
            "sys:repair:image:add",
            "sys:repair:image:edit",
            "sys:repair:image:del",
        }
        self.assertTrue(expected.issubset(codes))

    def test_api_routes_registered(self):
        import asgi

        paths = {r.path for r in asgi.app.routes}
        self.assertIn("/api/v1/repair-images/upload", paths)
        self.assertIn("/api/v1/repair-images/{image_id}", paths)
        self.assertIn("/api/v1/repair-images/{image_id}/content", paths)


if __name__ == "__main__":
    unittest.main()
