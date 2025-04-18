import unittest
from telegram import InlineKeyboardButton
from bot import build_quality_buttons

class TestTelegramVideoBot(unittest.TestCase):
    def test_quality_buttons_structure(self):
        formats = [
            {"format_id": "18", "ext": "mp4", "format_note": "360p"},
            {"format_id": "22", "ext": "mp4", "format_note": "720p"},
        ]
        buttons = build_quality_buttons(formats, "test_url")
        self.assertTrue(all(isinstance(b[0], InlineKeyboardButton) for b in buttons))
        self.assertIn("720p", buttons[1][0].text)

if __name__ == '__main__':
    unittest.main()
