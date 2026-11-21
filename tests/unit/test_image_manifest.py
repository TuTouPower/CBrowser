import json

import pytest

from scripts.image_manifest import ROLES, read_images


@pytest.mark.parametrize("mode,ref", [
    ("local", "sha256:" + "a" * 64),
    ("registry", "ghcr.io/example/image@sha256:" + "a" * 64),
])
def test_manifest_accepts_only_complete_pinned_images(tmp_path, mode, ref):
    path = tmp_path / "images.json"
    images = {role: ref for role in ROLES}
    path.write_text(json.dumps({"images": images}))
    assert read_images(path, mode) == images

    images["stream"] = "ghcr.io/example/stream:latest"
    path.write_text(json.dumps({"images": images}))
    with pytest.raises(ValueError, match="stream: expected an immutable"):
        read_images(path, mode)

    del images["stream"]
    path.write_text(json.dumps({"images": images}))
    with pytest.raises(ValueError, match="exactly the six"):
        read_images(path, mode)
