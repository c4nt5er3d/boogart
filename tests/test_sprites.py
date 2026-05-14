from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from boogart.core.growth import STAGE_IDS
from boogart.rendering.sprite import STAGE_SPRITE_FILES, render_boogart_sprite, sprite_asset_path


class SpriteTests(unittest.TestCase):
    def test_sprite_registry_has_all_growth_stages(self) -> None:
        self.assertEqual(set(STAGE_SPRITE_FILES), set(STAGE_IDS))

    def test_sprite_asset_paths_use_required_names(self) -> None:
        assets = Path("assets/sprites")
        self.assertEqual(sprite_asset_path(assets, "newborn").name, "boogart_01_newborn.png")
        self.assertEqual(sprite_asset_path(assets, "final").name, "boogart_08_final.png")

    def test_missing_asset_falls_back_to_placeholder_png(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "boogart.png"
            render_boogart_sprite(out, "changed", assets_dir=Path(tmp) / "missing")
            self.assertTrue(out.exists())
            self.assertGreater(out.stat().st_size, 0)

    def test_all_stage_placeholders_render(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for stage in STAGE_IDS:
                with self.subTest(stage=stage):
                    out = Path(tmp) / f"{stage}.png"
                    render_boogart_sprite(out, stage)
                    self.assertTrue(out.exists())
                    self.assertGreater(out.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
