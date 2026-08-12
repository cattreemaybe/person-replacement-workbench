import base64
import io
import tempfile
import unittest
from unittest.mock import Mock, patch
from pathlib import Path

from PIL import Image

import server


def data_url(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


class PersonReplaceTests(unittest.TestCase):
    def test_compat_config_reads_environment(self):
        with patch.dict("os.environ", {
            "OPENAI_COMPAT_BASE_URL": "https://relay.example/v1/",
            "OPENAI_COMPAT_API_KEY": "test-secret",
            "OPENAI_COMPAT_MODEL": "custom-image-model",
        }):
            self.assertEqual(
                server._compat_config(),
                ("https://relay.example/v1", "test-secret", "custom-image-model"),
            )

    def test_box_is_clamped_to_scene(self):
        self.assertEqual(server._clamp_box({"x": -5, "y": 3, "width": 80, "height": 80}, 60, 50), (0, 3, 60, 50))

    def test_strict_composite_keeps_every_pixel_outside_box(self):
        scene = Image.new("RGB", (160, 120), (20, 40, 60))
        crop_box = (20, 10, 140, 110)
        box = (50, 30, 110, 100)
        generated = Image.new("RGB", (120, 100), (230, 50, 30))
        result = server._strict_composite(scene, generated, crop_box, box, feather=12)
        for y in range(scene.height):
            for x in range(scene.width):
                if not (box[0] <= x < box[2] and box[1] <= y < box[3]):
                    self.assertEqual(result.getpixel((x, y)), scene.getpixel((x, y)))
        self.assertNotEqual(result.getpixel((80, 60)), scene.getpixel((80, 60)))

    def test_subject_mask_locks_pixels_inside_box_but_outside_person(self):
        scene = Image.new("RGB", (120, 100), (20, 40, 60))
        crop_box = (10, 10, 110, 90)
        box = (20, 15, 100, 85)
        generated = Image.new("RGB", (100, 80), (230, 50, 30))
        subject = Image.new("L", (100, 80), 0)
        from PIL import ImageDraw
        ImageDraw.Draw(subject).ellipse((35, 15, 65, 70), fill=255)
        result = server._strict_composite(scene, generated, crop_box, box, feather=4, subject_mask=subject)
        self.assertEqual(result.getpixel((25, 25)), scene.getpixel((25, 25)))
        self.assertNotEqual(result.getpixel((60, 50)), scene.getpixel((60, 50)))

    def test_expand_and_shrink_mask(self):
        from PIL import ImageDraw
        mask = Image.new("L", (50, 50), 0)
        ImageDraw.Draw(mask).rectangle((20, 20, 29, 29), fill=255)
        grown = server._adjust_mask(mask, 3)
        shrunk = server._adjust_mask(mask, -2)
        self.assertGreater(sum(grown.get_flattened_data()), sum(mask.get_flattened_data()))
        self.assertLess(sum(shrunk.get_flattened_data()), sum(mask.get_flattened_data()))

    def test_mask_png_keeps_black_background_and_white_subject(self):
        mask = Image.new("L", (20, 20), 0)
        from PIL import ImageDraw
        ImageDraw.Draw(mask).rectangle((6, 4, 13, 17), fill=255)
        encoded = data_url(mask)
        decoded = server._open_mask(encoded, (20, 20))
        self.assertEqual(decoded.getpixel((0, 0)), 0)
        self.assertEqual(decoded.getpixel((10, 10)), 255)

    def test_demo_request_creates_downloadable_png(self):
        scene = Image.new("RGB", (220, 180), (220, 210, 190))
        person = Image.new("RGB", (100, 140), (90, 120, 150))
        old_outputs = server.OUTPUTS
        try:
            with tempfile.TemporaryDirectory() as tmp:
                server.OUTPUTS = Path(tmp)
                response = server.create_result({
                    "scene": data_url(scene),
                    "person": data_url(person),
                    "box": {"x": 60, "y": 20, "width": 90, "height": 140},
                    "mode": "demo",
                    "feather": 8,
                })
                self.assertTrue(response["locked"])
                self.assertTrue((Path(tmp) / response["filename"]).is_file())
                self.assertTrue(response["image"].startswith("data:image/png;base64,"))
        finally:
            server.OUTPUTS = old_outputs

    def test_provider_url_result_is_not_downloaded(self):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"data": [{"url": "http://127.0.0.1/private"}]}
        scene = Image.new("RGB", (40, 40), "white")
        mask = Image.new("RGBA", (40, 40), "white")
        person = Image.new("RGB", (40, 40), "black")
        with patch("server.requests.post", return_value=response), patch("server.requests.get") as get:
            with self.assertRaisesRegex(RuntimeError, "仅接受 Base64"):
                server._call_openai(scene, mask, person, "token", "https://example.test/v1", "image-model", "")
            get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
