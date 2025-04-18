import unittest
from bot import validate_url, get_platform

class TestBotFunctions(unittest.TestCase):
    def test_validate_url(self):
        self.assertTrue(validate_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
        self.assertTrue(validate_url("https://www.instagram.com/p/Cz9yZx9vL2Q/"))
        self.assertFalse(validate_url("https://example.com"))

    def test_get_platform(self):
        self.assertEqual(get_platform("https://www.youtube.com/watch?v=dQw4w9WgXcQ"), "youtube")
        self.assertEqual(get_platform("https://www.instagram.com/p/Cz9yZx9vL2Q/"), "instagram")
        self.assertEqual(get_platform("https://example.com"), "unknown")

if __name__ == "__main__":
    unittest.main()
