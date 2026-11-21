"""Verify independently painted X11 chrome, menu, and content by pixel region."""

import json
import sys
from collections import Counter
from pathlib import Path

from PIL import Image, ImageChops


REGIONS = {
    "tab_strip": (390, 5, 750, 28),
    "address_bar": (700, 47, 760, 51),
    "toolbar": (400, 81, 600, 101),
    "menu": (920, 270, 988, 410),
}
MENU_AREA = (780, 105, 1119, 695)
BODY = (600, 360, 700, 500)
NATIVE_DARK = {"then_dark", "parallel_dark", "gtk_override_dark"}
CASES = {
    "baseline_dark",
    "first_light",
    "then_dark",
    "back_light",
    "parallel_dark",
    "parallel_light",
    "gtk_dark_requested",
    "gtk_override_dark",
}


def read_rgb(path):
    with Image.open(path) as image:
        return image.convert("RGB")


def dominant(image, area):
    histogram = Counter(image.crop(area).get_flattened_data())
    return histogram.most_common(1)[0][0]


def verify(evidence_dir):
    runtime = json.loads((evidence_dir / "runtime_results.json").read_text())
    assert set(runtime) == CASES
    assert runtime["parallel_light"]["display"] != runtime["parallel_dark"]["display"]
    assert runtime["parallel_light"]["profile"] != runtime["parallel_dark"]["profile"]
    report = {}
    for label, record in runtime.items():
        assert record["engine"] == "146.0.7680.177.3"
        window = read_rgb(evidence_dir / f"{label}_window.png")
        menu = read_rgb(evidence_dir / f"{label}_menu.png")
        colors = {
            name: dominant(menu if name == "menu" else window, region)
            for name, region in REGIONS.items()
        }
        for name, rgb in colors.items():
            assert (max(rgb) < 90) if label in NATIVE_DARK else (min(rgb) > 185), (
                label, name, rgb
            )
        menu_diff = ImageChops.difference(window.crop(MENU_AREA), menu.crop(MENU_AREA))
        assert menu_diff.getbbox() is not None, (label, "Menu remained closed")
        body = dominant(window, BODY)
        assert body == (
            (32, 33, 36) if record["adaptive"]["scheme"] == "dark" else (244, 245, 246)
        )
        report[label] = {"native": colors, "body": body, **record}
    white = read_rgb(evidence_dir / "dark_fixed_white.png")
    assert dominant(white, BODY) == (255, 255, 255)
    assert max(dominant(white, REGIONS["tab_strip"])) < 90
    return report


if __name__ == "__main__":
    print(json.dumps(verify(Path(sys.argv[1])), indent=2))
