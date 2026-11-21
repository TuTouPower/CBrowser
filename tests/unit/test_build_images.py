import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

from scripts.image_manifest import ROLES

ROOT = Path(__file__).resolve().parents[2]


def test_build_downloads_and_locks_all_images(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copy(ROOT / "scripts/build_images.sh", scripts)
    config = tmp_path / "config"
    config.mkdir()
    bundle = b"simulated locked archive"
    lock = {
        "url": "https://assets.example/fonts.tar.zst",
        "sha256": hashlib.sha256(bundle).hexdigest(),
    }
    (config / "font_assets.lock.json").write_text(json.dumps(lock))
    binaries = tmp_path / "bin"
    binaries.mkdir()
    download = binaries / "curl"
    download.write_text(
        "#!/bin/bash\n"
        '[[ "${*: -1}" = https://assets.example/fonts.tar.zst ]] || exit 2\n'
        'printf "%s" "$FONT_TEST_BYTES" > "${@: -2:1}"\n'
    )
    docker = binaries / "docker"
    docker.write_text(
        "#!/bin/bash\n"
        'echo "$*" >> "$FONT_TEST_LOG"\n'
        'if [ "$1" = image ]; then printf "sha256:%064d\\n" 0; fi\n'
    )
    for script in (download, docker):
        script.chmod(0o755)
    log = tmp_path / "docker.log"
    env = {
        **os.environ,
        "PATH": f"{binaries}:{os.environ['PATH']}",
        "CBROWSER_IMAGE_TAG": "fixture",
        "PYTHONPATH": str(ROOT / "src/backend"),
        "FONT_TEST_BYTES": bundle.decode(),
        "FONT_TEST_LOG": str(log),
    }
    env.pop("CBROWSER_FONT_ARCHIVE", None)
    (tmp_path / "src").mkdir()
    (tmp_path / "src/backend").symlink_to(ROOT / "src/backend")
    result = subprocess.run(["bash", str(scripts / "build_images.sh")], env=env, capture_output=True)
    assert result.returncode == 0, result.stderr.decode()
    images = json.loads((tmp_path / ".scratch/images.json").read_text())["images"]
    assert set(images) == set(ROLES)
    calls = log.read_text().splitlines()
    assert sum(line.startswith("buildx build") for line in calls) == 6
    assert sum("--build-context font_assets=" in line for line in calls) == 1
    assert any("caddy_runtime/Dockerfile" in line for line in calls)
