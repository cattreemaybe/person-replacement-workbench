"""Download the MobileSAM checkpoint and verify it before installation."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests


ROOT = Path(__file__).resolve().parent
DESTINATION = ROOT / "models" / "mobile_sam.pt"
URL = "https://raw.githubusercontent.com/ChaoningZhang/MobileSAM/master/weights/mobile_sam.pt"
SHA256 = "6dbb90523a35330fedd7f1d3dfc66f995213d81b29a5ca8108dbcdd4e37d6c2f"
ALLOWED_HOST = "raw.githubusercontent.com"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    if DESTINATION.is_file() and file_sha256(DESTINATION) == SHA256:
        print(f"MobileSAM 模型已就绪：{DESTINATION}")
        return 0

    DESTINATION.parent.mkdir(exist_ok=True)
    temporary = DESTINATION.with_suffix(".pt.part")
    print("正在从 MobileSAM 官方仓库下载模型（约 39 MB）……")
    try:
        parsed = urlparse(URL)
        if parsed.scheme != "https" or parsed.hostname != ALLOWED_HOST:
            raise RuntimeError("模型下载地址不是允许的官方 HTTPS 地址。")
        with requests.get("https://raw.githubusercontent.com/ChaoningZhang/MobileSAM/master/weights/mobile_sam.pt", stream=True, timeout=(15, 180)) as response:
            response.raise_for_status()
            digest = hashlib.sha256()
            with temporary.open("wb") as handle:
                for chunk in response.iter_content(1024 * 1024):
                    if chunk:
                        digest.update(chunk)
                        handle.write(chunk)
        if digest.hexdigest() != SHA256:
            temporary.unlink(missing_ok=True)
            print("下载文件校验失败，已删除临时文件。", file=sys.stderr)
            return 1
        temporary.replace(DESTINATION)
        print(f"模型下载完成：{DESTINATION}")
        return 0
    except (OSError, requests.RequestException) as exc:
        temporary.unlink(missing_ok=True)
        print(f"模型下载失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
