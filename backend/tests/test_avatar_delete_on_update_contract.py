import unittest


class TestAvatarDeleteOnUpdateContract(unittest.TestCase):
    def test_user_model_has_avatar_key_field(self):
        from app.models.orm.user import User

        self.assertIn("avatar_key", getattr(User, "_meta").fields_map)


if __name__ == "__main__":
    unittest.main()
