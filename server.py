from __future__ import annotations

import base64
import io
import json
import os
import secrets
import threading
import time
import warnings
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageOps


ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
OUTPUTS = ROOT / "outputs"
MODEL_PATH = ROOT / "models" / "mobile_sam.pt"
MAX_BODY_BYTES = 42 * 1024 * 1024
HOST = "127.0.0.1"
PORT = int(os.environ.get("PERSON_REPLACE_PORT", "8765"))
_SAM_PREDICTOR = None
_SAM_LOCK = threading.Lock()


def _load_dotenv(path: Path) -> None:
    """Load a small .env file without adding a runtime dependency."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(ROOT / ".env")


def _compat_config() -> tuple[str, str, str]:
    base_url = os.environ.get("OPENAI_COMPAT_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
    api_key = os.environ.get("OPENAI_COMPAT_API_KEY", "").strip() or os.environ.get("OPENAI_API_KEY", "").strip()
    model = os.environ.get("OPENAI_COMPAT_MODEL", "gpt-image-2").strip() or "gpt-image-2"
    return base_url, api_key, model


def _decode_data_url(value: str) -> bytes:
    if not isinstance(value, str) or "," not in value:
        raise ValueError("图片数据无效，请重新上传。")
    header, encoded = value.split(",", 1)
    if not header.startswith("data:image/"):
        raise ValueError("只支持图片文件。")
    try:
        return base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ValueError("图片无法读取，请换一张 JPG、PNG 或 WEBP。") from exc


def _open_rgb(value: str) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(_decode_data_url(value)))
        image = ImageOps.exif_transpose(image)
        return image.convert("RGB")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("图片格式无法识别，请换一张 JPG、PNG 或 WEBP。") from exc


def _open_mask(value: str, size: tuple[int, int]) -> Image.Image:
    try:
        mask = Image.open(io.BytesIO(_decode_data_url(value))).convert("L")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("人物轮廓遮罩无法读取，请重新识别。") from exc
    if mask.size != size:
        raise ValueError("人物轮廓遮罩尺寸与场景图不一致，请重新识别。")
    return mask.point(lambda p: 255 if p >= 128 else 0)


def _as_png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _clamp_box(raw_box: dict, width: int, height: int) -> tuple[int, int, int, int]:
    try:
        x = round(float(raw_box["x"]))
        y = round(float(raw_box["y"]))
        w = round(float(raw_box["width"]))
        h = round(float(raw_box["height"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("人物选框无效，请重新框选。") from exc
    x1 = max(0, min(width - 1, x))
    y1 = max(0, min(height - 1, y))
    x2 = max(x1 + 1, min(width, x + w))
    y2 = max(y1 + 1, min(height, y + h))
    if (x2 - x1) * (y2 - y1) < 900:
        raise ValueError("人物选框太小，请把整个人框进去。")
    return x1, y1, x2, y2


def _expanded_crop(box: tuple[int, int, int, int], width: int, height: int) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = box
    margin_x = max(48, round((x2 - x1) * 0.45))
    margin_y = max(48, round((y2 - y1) * 0.30))
    return max(0, x1 - margin_x), max(0, y1 - margin_y), min(width, x2 + margin_x), min(height, y2 + margin_y)


def _build_crop_and_mask(scene: Image.Image, box: tuple[int, int, int, int]) -> tuple[Image.Image, Image.Image, tuple[int, int, int, int]]:
    crop_box = _expanded_crop(box, *scene.size)
    crop = scene.crop(crop_box)
    bx1, by1, bx2, by2 = box
    cx1, cy1, _, _ = crop_box
    local = (bx1 - cx1, by1 - cy1, bx2 - cx1, by2 - cy1)

    # OpenAI image-edit masks use transparent pixels for the editable region.
    mask = Image.new("RGBA", crop.size, (255, 255, 255, 255))
    draw = ImageDraw.Draw(mask)
    draw.rectangle(local, fill=(255, 255, 255, 0))
    return crop, mask, crop_box


def _get_sam_predictor():
    global _SAM_PREDICTOR
    if _SAM_PREDICTOR is not None:
        return _SAM_PREDICTOR
    if not MODEL_PATH.is_file():
        raise RuntimeError("MobileSAM 模型权重不存在，请检查 models/mobile_sam.pt。")
    try:
        import torch
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from mobile_sam import SamPredictor, sam_model_registry
        model = sam_model_registry["vit_t"](checkpoint=str(MODEL_PATH))
        model.to(device="cpu")
        model.eval()
        _SAM_PREDICTOR = SamPredictor(model)
        return _SAM_PREDICTOR
    except Exception as exc:
        raise RuntimeError(f"MobileSAM 无法启动：{exc}") from exc


def _adjust_mask(mask: Image.Image, expand: int) -> Image.Image:
    expand = max(-20, min(32, int(expand)))
    if expand == 0:
        return mask
    # PIL filters require odd kernels. Positive values grow the mask; negative
    # values shrink it. Cap the kernel to keep memory use predictable.
    kernel = min(65, abs(expand) * 2 + 1)
    return mask.filter(ImageFilter.MaxFilter(kernel) if expand > 0 else ImageFilter.MinFilter(kernel))


def segment_person(scene: Image.Image, box: tuple[int, int, int, int], expand: int = 4) -> tuple[Image.Image, float]:
    try:
        import numpy as np
        import torch
    except ImportError as exc:
        raise RuntimeError("人物轮廓依赖未安装，请用 start.command 启动项目环境。") from exc
    predictor = _get_sam_predictor()
    image_array = np.asarray(scene)
    input_box = np.array(box, dtype=np.float32)
    with _SAM_LOCK, torch.inference_mode():
        predictor.set_image(image_array)
        masks, scores, _ = predictor.predict(box=input_box, multimask_output=True)
    best = int(np.argmax(scores))
    binary = Image.fromarray((masks[best].astype("uint8") * 255), mode="L")
    binary = _adjust_mask(binary, expand)
    selected_pixels = sum(1 for value in binary.getdata() if value)
    coverage = selected_pixels / (scene.width * scene.height)
    if coverage < 0.001:
        raise RuntimeError("没有识别到有效人物轮廓，请把矩形框画得更贴近人物。")
    box_area = max(1, (box[2] - box[0]) * (box[3] - box[1]))
    relative_coverage = selected_pixels / box_area
    if coverage > 0.72 or relative_coverage > 2.5:
        raise RuntimeError("识别结果覆盖范围异常大，请把矩形框画得更贴近人物后重试。")
    return binary, float(scores[best])


def _crop_with_model_mask(scene: Image.Image, box: tuple[int, int, int, int], full_mask: Image.Image) -> tuple[Image.Image, Image.Image, Image.Image, tuple[int, int, int, int]]:
    crop_box = _expanded_crop(box, *scene.size)
    crop = scene.crop(crop_box)
    subject_mask = full_mask.crop(crop_box)
    api_mask = Image.new("RGBA", crop.size, (255, 255, 255, 255))
    api_mask.putalpha(ImageOps.invert(subject_mask))
    return crop, api_mask, subject_mask, crop_box


def _strict_composite(scene: Image.Image, generated_crop: Image.Image, crop_box: tuple[int, int, int, int], box: tuple[int, int, int, int], feather: int, subject_mask: Image.Image | None = None) -> Image.Image:
    crop_size = (crop_box[2] - crop_box[0], crop_box[3] - crop_box[1])
    generated_crop = generated_crop.convert("RGB").resize(crop_size, Image.Resampling.LANCZOS)
    result = scene.copy()
    bx1, by1, bx2, by2 = box
    cx1, cy1, _, _ = crop_box
    local_box = (bx1 - cx1, by1 - cy1, bx2 - cx1, by2 - cy1)

    if subject_mask is not None:
        alpha = subject_mask.convert("L").resize(crop_size, Image.Resampling.NEAREST)
        clip = alpha.copy()
    else:
        alpha = Image.new("L", crop_size, 0)
        # Pillow rectangles include the right and bottom endpoints, while browser
        # selection boxes use half-open coordinates. Subtract one pixel to keep the
        # strict lock guarantee at the boundary as well.
        mask_box = (local_box[0], local_box[1], local_box[2] - 1, local_box[3] - 1)
        ImageDraw.Draw(alpha).rectangle(mask_box, fill=255)
        clip = alpha.copy()
    feather = max(0, min(24, int(feather)))
    if feather:
        alpha = alpha.filter(ImageFilter.GaussianBlur(feather / 2))
        # The blur can leak outside the user box; clip it so strict mode remains exact.
        alpha = Image.composite(alpha, Image.new("L", crop_size, 0), clip)

    original_crop = scene.crop(crop_box)
    blended = Image.composite(generated_crop, original_crop, alpha)
    result.paste(blended, (crop_box[0], crop_box[1]))
    return result


def _demo_generated_crop(crop: Image.Image, box: tuple[int, int, int, int], crop_box: tuple[int, int, int, int]) -> Image.Image:
    generated = crop.copy()
    x1, y1, x2, y2 = box
    cx1, cy1, _, _ = crop_box
    local = (x1 - cx1, y1 - cy1, x2 - cx1, y2 - cy1)
    overlay = Image.new("RGBA", crop.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle(local, fill=(190, 53, 38, 82), outline=(190, 53, 38, 230), width=max(2, crop.width // 220))
    draw.line((local[0], local[1], local[2], local[3]), fill=(255, 240, 220, 210), width=3)
    draw.line((local[2], local[1], local[0], local[3]), fill=(255, 240, 220, 210), width=3)
    return Image.alpha_composite(generated.convert("RGBA"), overlay).convert("RGB")


def _call_openai(scene_crop: Image.Image, mask: Image.Image, person: Image.Image, api_key: str, base_url: str, model: str, prompt_note: str) -> Image.Image:
    prompt = (
        "Image 1 is a crop from the target scene. Image 2 is the identity reference person. "
        "Replace only the person inside the transparent mask in Image 1 with the person from Image 2. "
        "Preserve the target person's exact pose, body position, scale, camera perspective, occlusions, and interaction with the scene. "
        "Transfer the reference person's recognizable facial identity, hair, and overall appearance naturally. "
        "Match the scene lighting, color, focus, grain, and shadows. Do not add or remove any other person or object. "
        "Do not alter pixels outside the masked region. No text, watermark, border, or collage."
    )
    if prompt_note.strip():
        prompt += " Additional user instruction: " + prompt_note.strip()[:600]

    files = [
        ("image[]", ("scene.png", _as_png_bytes(scene_crop), "image/png")),
        ("image[]", ("person-reference.png", _as_png_bytes(person), "image/png")),
        ("mask", ("mask.png", _as_png_bytes(mask), "image/png")),
    ]
    data = {
        "model": model,
        "prompt": prompt,
        "quality": "high",
        "output_format": "png",
        "size": "auto",
    }
    try:
        response = requests.post(
            f"{base_url}/images/edits",
            headers={"Authorization": f"Bearer {api_key}"},
            files=files,
            data=data,
            timeout=240,
        )
    except requests.RequestException as exc:
        raise RuntimeError("无法连接图片服务，请检查网络后重试。") from exc
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"图片服务返回了无法识别的内容（HTTP {response.status_code}）。") from exc
    if response.status_code >= 400:
        message = payload.get("error", {}).get("message", "图片服务调用失败。")
        hint = ""
        if model != "gpt-image-2":
            hint = f" 当前配置模型为 {model}；若中转未给它映射图片编辑能力，请在 .env 中改为 gpt-image-2。"
        raise RuntimeError(f"图片服务调用失败：{message}{hint}")
    try:
        item = payload["data"][0]
        if item.get("b64_json"):
            image_bytes = base64.b64decode(item["b64_json"])
        elif item.get("url"):
            # Do not fetch provider-controlled URLs from this local service.
            # A compromised or misconfigured provider could otherwise use the
            # server to reach localhost or private-network resources (SSRF).
            raise ValueError("图片服务只返回了下载链接；为保护本机网络，本项目仅接受 Base64 图片结果。")
        else:
            raise KeyError("missing image payload")
        return Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except RuntimeError:
        raise
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    except Exception as exc:
        raise RuntimeError("图片服务没有返回可用图片，请重试。") from exc


def create_result(payload: dict) -> dict:
    scene = _open_rgb(payload.get("scene", ""))
    person = _open_rgb(payload.get("person", ""))
    if scene.width * scene.height > 24_000_000 or person.width * person.height > 24_000_000:
        raise ValueError("图片尺寸过大，请将单张图片控制在约 2400 万像素以内。")
    box = _clamp_box(payload.get("box", {}), *scene.size)
    mask_value = payload.get("mask", "")
    if mask_value:
        full_mask = _open_mask(mask_value, scene.size)
        crop, mask, subject_mask, crop_box = _crop_with_model_mask(scene, box, full_mask)
    else:
        crop, mask, crop_box = _build_crop_and_mask(scene, box)
        subject_mask = None
    mode = payload.get("mode", "openai")
    base_url, api_key, model = _compat_config()

    if mode == "demo":
        generated = _demo_generated_crop(crop, box, crop_box)
    else:
        if not api_key:
            raise ValueError("请填写 OpenAI API Key，或先选择“演示模式”测试操作流程。")
        generated = _call_openai(crop, mask, person, api_key, base_url, model, str(payload.get("note", "")))

    result = _strict_composite(scene, generated, crop_box, box, int(payload.get("feather", 8)), subject_mask)
    OUTPUTS.mkdir(exist_ok=True)
    filename = f"person-replaced-{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(2)}.png"
    result.save(OUTPUTS / filename, format="PNG")
    encoded = base64.b64encode(_as_png_bytes(result)).decode("ascii")
    return {
        "image": f"data:image/png;base64,{encoded}",
        "download": f"/outputs/{filename}",
        "filename": filename,
        "mode": mode,
        "locked": True,
        "box": {"x": box[0], "y": box[1], "width": box[2] - box[0], "height": box[3] - box[1]},
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "PersonReplaceLocal/1.0"

    def log_message(self, fmt: str, *args) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, path: Path) -> None:
        if not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        mime = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "application/javascript; charset=utf-8", ".png": "image/png"}.get(path.suffix.lower(), "application/octet-stream")
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store" if path.suffix == ".html" else "public, max-age=300")
        if path.parent == OUTPUTS:
            self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        route = urlparse(self.path).path
        if route == "/api/health":
            base_url, api_key, model = _compat_config()
            self._json(200, {
                "ok": True,
                "apiKeyConfigured": bool(api_key),
                "provider": urlparse(base_url).hostname or base_url,
                "model": model,
            })
            return
        if route.startswith("/outputs/"):
            name = Path(route).name
            self._serve_file(OUTPUTS / name)
            return
        relative = "index.html" if route == "/" else route.lstrip("/")
        if ".." in Path(relative).parts:
            self.send_error(HTTPStatus.BAD_REQUEST)
            return
        self._serve_file(STATIC / relative)

    def do_POST(self) -> None:
        route = urlparse(self.path).path
        if route not in {"/api/replace", "/api/segment"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY_BYTES:
                raise ValueError("上传内容为空或超过 42MB，请压缩图片后重试。")
            payload = json.loads(self.rfile.read(length))
            if route == "/api/segment":
                scene = _open_rgb(payload.get("scene", ""))
                box = _clamp_box(payload.get("box", {}), *scene.size)
                mask, score = segment_person(scene, box, int(payload.get("expand", 4)))
                encoded = base64.b64encode(_as_png_bytes(mask)).decode("ascii")
                self._json(200, {"mask": f"data:image/png;base64,{encoded}", "score": round(score, 4)})
            else:
                self._json(200, create_result(payload))
        except (ValueError, json.JSONDecodeError) as exc:
            self._json(400, {"error": str(exc)})
        except RuntimeError as exc:
            self._json(502, {"error": str(exc)})
        except Exception as exc:
            print("Unexpected error:", repr(exc))
            self._json(500, {"error": "处理失败，请检查终端日志后重试。"})


def main() -> None:
    OUTPUTS.mkdir(exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}"
    print(f"人物替换工作台已启动：{url}")
    print("按 Control+C 停止。输出文件保存在 outputs 文件夹。")
    threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
