import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import build_card_html, crop_card, normalize_payload  # noqa: E402


class CropCardTest(unittest.TestCase):
    def test_crops_transparent_margins(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "card.png"
            image = Image.new("RGBA", (800, 720), (0, 0, 0, 0))
            for x in range(100, 700):
                for y in range(50, 500):
                    image.putpixel((x, y), (255, 255, 255, 255))
            image.save(path)

            crop_card(str(path), pad=18)

            with Image.open(path) as cropped:
                # 内容 600x450 + 两侧各 18px
                self.assertEqual(cropped.size, (636, 486))

    def test_handles_opaque_background(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "card.png"
            image = Image.new("RGBA", (800, 720), (244, 245, 247, 255))
            for x in range(120, 680):
                for y in range(80, 480):
                    image.putpixel((x, y), (255, 255, 255, 255))
            image.save(path)

            crop_card(str(path), pad=10)
            with Image.open(path) as cropped:
                self.assertLess(cropped.height, 720)


class TemplateTest(unittest.TestCase):
    def test_template_has_no_background(self):
        html = build_card_html(normalize_payload({"title": "x"}))
        self.assertIn("background: transparent", html)


if __name__ == "__main__":
    unittest.main()
