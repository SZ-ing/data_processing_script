"""从 resources/icons/app.svg 内嵌 PNG 生成 icons/app.ico（供 Nuitka 使用）。"""
from __future__ import annotations

import base64
import re
from io import BytesIO
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SVG_PATH = ROOT / "resources" / "icons" / "app.svg"
ICO_PATH = ROOT / "icons" / "app.ico"


def main() -> None:
    text = SVG_PATH.read_text(encoding="utf-8")
    m = re.search(r"data:image/png;base64,([^'\"]+)", text)
    if not m:
        raise SystemExit(f"未在 {SVG_PATH} 中找到内嵌 PNG")

    png_bytes = base64.b64decode(m.group(1))
    im = Image.open(BytesIO(png_bytes)).convert("RGBA")

    ICO_PATH.parent.mkdir(parents=True, exist_ok=True)
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    images = [im.resize(s, Image.Resampling.LANCZOS) for s in sizes]
    images[0].save(
        ICO_PATH,
        format="ICO",
        sizes=[(img.width, img.height) for img in images],
        append_images=images[1:],
    )
    print(f"已写入: {ICO_PATH}")


if __name__ == "__main__":
    main()
