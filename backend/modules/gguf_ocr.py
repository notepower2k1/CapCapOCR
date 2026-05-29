from __future__ import annotations

import base64
from io import BytesIO
import os
from pathlib import Path
from threading import Lock

from PIL import Image

from backend.modules.errors import OCRDependencyError, OCRError
from backend.modules.llama_paddle_handler import PaddleOCRChatHandler


DEFAULT_MODEL_DIR = Path(__file__).resolve().parents[2] / "ocr_ai_model"
DEFAULT_MODEL_PATH = DEFAULT_MODEL_DIR / "PaddleOCR-VL-For-Manga-BF16.gguf"
DEFAULT_MMPROJ_PATH = DEFAULT_MODEL_DIR / "PaddleOCR-VL-For-Manga-mmproj-BF16.gguf"


class GGUFMangaOCRRecognizer:
    def __init__(self) -> None:
        self._llama = None
        self._lock = Lock()
        self.model_path = Path(os.getenv("GGUF_OCR_MODEL_PATH", DEFAULT_MODEL_PATH))
        self.mmproj_path = Path(os.getenv("GGUF_OCR_MMPROJ_PATH", DEFAULT_MMPROJ_PATH))
        self.n_ctx = int(os.getenv("GGUF_OCR_N_CTX", "4096"))
        self.n_threads = int(os.getenv("GGUF_OCR_N_THREADS", str(os.cpu_count() or 4)))
        self.n_gpu_layers = int(os.getenv("GGUF_OCR_N_GPU_LAYERS", "-1"))

    def _get_instance(self):
        if self._llama is not None:
            return self._llama

        with self._lock:
            if self._llama is not None:
                return self._llama

            if not self.model_path.exists():
                raise OCRDependencyError(
                    f"GGUF OCR model not found at `{self.model_path}`."
                )
            if not self.mmproj_path.exists():
                raise OCRDependencyError(
                    f"GGUF OCR mmproj model not found at `{self.mmproj_path}`."
                )

            try:
                from llama_cpp import Llama
            except ImportError as exc:
                raise OCRDependencyError(
                    "llama-cpp-python is missing. Install it to enable the GGUF manga OCR engine."
                ) from exc

            try:
                chat_handler = PaddleOCRChatHandler(
                    clip_model_path=str(self.mmproj_path),
                    verbose=False,
                )
                self._llama = Llama(
                    model_path=str(self.model_path),
                    chat_handler=chat_handler,
                    n_ctx=self.n_ctx,
                    n_threads=self.n_threads,
                    n_gpu_layers=self.n_gpu_layers,
                    offload_kqv=True,
                    flash_attn=True,
                    verbose=False,
                )
            except Exception as exc:  # pragma: no cover - runtime varies by platform
                raise OCRDependencyError(
                    "Failed to initialize the GGUF manga OCR model. Verify the GGUF files "
                    "and your llama-cpp-python runtime."
                ) from exc

            return self._llama

    def recognize(self, image: Image.Image) -> str:
        llama = self._get_instance()
        image_url = self._image_to_data_url(image)
        prompt = "OCR:"

        try:
            response = llama.create_chat_completion(
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": image_url}},
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
                temperature=0.0,
                top_p=0.9,
                max_tokens=256,
            )
        except Exception as exc:  # pragma: no cover - runtime varies by platform
            raise OCRError(f"GGUF OCR inference failed: {exc}") from exc

        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise OCRError("GGUF OCR returned an unexpected response shape.") from exc

        return str(content).strip()

    def _image_to_data_url(self, image: Image.Image) -> str:
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        payload = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/png;base64,{payload}"
