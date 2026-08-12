"""One paid end-to-end smoke test using synthetic assets only."""

import base64
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import server  # noqa: E402


def as_data_url(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def main() -> None:
    result = server.create_result({
        "scene": as_data_url(ROOT / "test-assets" / "scene.png"),
        "person": as_data_url(ROOT / "test-assets" / "person.png"),
        "box": {"x": 455, "y": 180, "width": 230, "height": 500},
        "mode": "openai",
        "note": "Keep the simple flat illustration style of the synthetic test scene.",
        "feather": 8,
    })
    print(f"ok={result['locked']} file={result['filename']} model={server._compat_config()[2]}")


if __name__ == "__main__":
    main()
