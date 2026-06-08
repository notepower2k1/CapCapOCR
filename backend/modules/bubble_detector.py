from __future__ import annotations

import os
from pathlib import Path
from threading import Lock
from typing import Any
import math

from backend.modules.errors import OCRDependencyError, OCRError


DEFAULT_MODEL_DIR = Path(__file__).resolve().parents[2] / "ocr_ai_model"
DEFAULT_MODEL_PATH = DEFAULT_MODEL_DIR / "yolov8m_seg-speech-bubble.pt"


class BubbleDetector:
    def __init__(self) -> None:
        self._model: Any | None = None
        self._lock = Lock()
        self.model_path = os.getenv("BUBBLE_DETECT_MODEL_PATH", str(DEFAULT_MODEL_PATH))
        self.confidence = float(os.getenv("BUBBLE_DETECT_CONF", "0.2"))
        self.iou = float(os.getenv("BUBBLE_DETECT_IOU", "0.5"))
        self.max_det = int(os.getenv("BUBBLE_DETECT_MAX", "64"))

    def _get_model(self):
        if self._model is not None:
            return self._model

        with self._lock:
            if self._model is not None:
                return self._model

            try:
                from ultralytics import YOLO
            except ImportError as exc:
                raise OCRDependencyError(
                    "ultralytics is missing. Install it to enable YOLO bubble detection."
                ) from exc

            try:
                self._model = YOLO(self.model_path)
            except Exception as exc:  # pragma: no cover
                raise OCRDependencyError(
                    f"Failed to load bubble detector model from `{self.model_path}`."
                ) from exc

            return self._model

    def detect(self, image_bgr: Any) -> list[list[list[int]]]:
        model = self._get_model()

        try:
            results = model.predict(
                source=image_bgr,
                conf=self.confidence,
                iou=self.iou,
                max_det=self.max_det,
                verbose=False,
            )
        except Exception as exc:  # pragma: no cover
            raise OCRError(f"Bubble detection failed: {exc}") from exc

        if not results:
            return []

        result = results[0]
        polygons = self._extract_masks(result)
        if polygons:
            return polygons
        return self._extract_boxes(result)

    def _extract_masks(self, result: Any) -> list[list[list[int]]]:
        masks = getattr(result, "masks", None)
        if masks is None or getattr(masks, "xy", None) is None:
            return []

        polygons: list[list[list[int]]] = []
        for points in masks.xy:
            if points is None or len(points) < 3:
                continue
            contour = [[int(round(x)), int(round(y))] for x, y in points]
            polygons.append(self._simplify_polygon(contour))
        return polygons

    def _extract_boxes(self, result: Any) -> list[list[list[int]]]:
        boxes = getattr(result, "boxes", None)
        if boxes is None or getattr(boxes, "xyxy", None) is None:
            return []

        polygons: list[list[list[int]]] = []
        for xyxy in boxes.xyxy.tolist():
            if len(xyxy) < 4:
                continue
            left, top, right, bottom = [int(round(value)) for value in xyxy[:4]]
            polygons.append(
                [
                    [left, top],
                    [right, top],
                    [right, bottom],
                    [left, bottom],
                ]
            )
        return polygons

    def _simplify_polygon(self, contour: list[list[int]], max_points: int = 24) -> list[list[int]]:
        deduped: list[list[int]] = []
        for point in contour:
            if not deduped or deduped[-1] != point:
                deduped.append(point)

        if len(deduped) <= max_points:
            return deduped

        perimeter = self._polygon_perimeter(deduped)
        epsilon = max(perimeter * 0.01, 2.0)

        try:
            import cv2
            import numpy as np

            array = np.array(deduped, dtype=np.int32).reshape((-1, 1, 2))
            approximated = cv2.approxPolyDP(array, epsilon, True).reshape((-1, 2)).tolist()
            simplified = [[int(x), int(y)] for x, y in approximated]
            if len(simplified) >= 3 and len(simplified) <= max_points:
                return simplified
        except Exception:
            pass

        step = math.ceil(len(deduped) / max_points)
        sampled = deduped[::step]
        return sampled if len(sampled) >= 3 else deduped[:max_points]

    def _polygon_perimeter(self, contour: list[list[int]]) -> float:
        if len(contour) < 2:
            return 0.0
        total = 0.0
        for index, point in enumerate(contour):
            next_point = contour[(index + 1) % len(contour)]
            total += math.dist(point, next_point)
        return total
