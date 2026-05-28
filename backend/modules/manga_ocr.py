from __future__ import annotations

from typing import Any

from PIL import Image

from backend.modules.errors import OCRDependencyError


class MangaOCRRecognizer:
    def __init__(self) -> None:
        self._instance: Any | None = None

    def _get_instance(self) -> Any:
        if self._instance is not None:
            return self._instance

        try:
            from manga_ocr import MangaOcr
        except ImportError as exc:
            raise OCRDependencyError(
                "manga-ocr is missing. Activate the virtual environment and run "
                "`pip install -r backend/requirements.ja.txt`."
            ) from exc

        try:
            self._instance = MangaOcr()
        except Exception as exc:  # pragma: no cover - model bootstrap depends on runtime
            raise OCRDependencyError(
                "manga-ocr failed to initialize. Verify the transformers/torch stack and "
                "network access for first-time model download."
            ) from exc

        return self._instance

    def recognize(self, image: Image.Image) -> str:
        model = self._get_instance()
        result = model(image)
        return str(result).strip()
