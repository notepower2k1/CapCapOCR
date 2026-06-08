from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any
import unicodedata
import cv2
import numpy as np
from PIL import ImageOps

from backend.modules.bubble_detector import BubbleDetector
from backend.modules.errors import OCRDependencyError, OCRError
from backend.modules.image_utils import (
    crop_manga_bubble_region,
    crop_polygon_region,
    infer_direction,
    load_image_from_bytes,
    median_rect_size,
    normalize_bbox,
    rect_area,
    rect_center,
    rect_contains,
    rect_from_bbox,
    rect_gap_x,
    rect_gap_y,
    rect_height,
    rect_intersection_area,
    rect_width,
    union_bbox,
)
from backend.modules.gguf_ocr import GGUFMangaOCRRecognizer
from backend.modules.manga_ocr import MangaOCRRecognizer
from backend.schemas.block import ImageMeta, OCRResponse, TextBlock

@dataclass
class OCRConfig:
    use_angle_cls: bool = True
    lang: str = "japan"
    region_crop_padding: int = 20
    line_crop_padding: int = 10
    whole_image_coverage_threshold: float = 0.72
    nested_box_overlap_ratio: float = 0.8
    nested_box_area_ratio: float = 0.28
    small_group_area_ratio: float = 0.18
    small_group_distance_scale: float = 3.0


class OCREngine:
    def __init__(self, config: OCRConfig | None = None) -> None:
        self.config = config or OCRConfig()
        self._ocr_instances: dict[str, Any] = {}
        self._manga_ocr = MangaOCRRecognizer()
        self._gguf_ocr = GGUFMangaOCRRecognizer()
        self._bubble_detector = BubbleDetector()

    def _get_instance(self, paddle_lang: str) -> Any:
        if paddle_lang in self._ocr_instances:
            return self._ocr_instances[paddle_lang]

        try:
            # Preload torch before PaddleOCR on Windows to avoid a transient
            # DLL-loading conflict through albumentations.pytorch.
            import torch  # noqa: F401
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise OCRDependencyError(
                "PaddleOCR or PaddlePaddle is missing. Activate the virtual environment "
                "and run `pip install -r backend/requirements.txt`."
            ) from exc

        try:
            instance = PaddleOCR(
                use_angle_cls=self.config.use_angle_cls,
                lang=paddle_lang,
                show_log=False,
                enable_mkldnn=False,
            )
        except Exception as exc:  # pragma: no cover - depends on runtime environment
            raise OCRDependencyError(
                "PaddleOCR failed to initialize. Python 3.11 is the recommended runtime "
                "for the Paddle stack in this project."
            ) from exc

        self._ocr_instances[paddle_lang] = instance
        return instance

    def process_image(
        self,
        image_bytes: bytes,
        source_lang: str = "ja",
        ocr_engine: str = "auto",
        detection_engine: str = "text",
    ) -> OCRResponse:
        try:
            image_array, width, height = load_image_from_bytes(image_bytes)
        except ValueError as exc:
            raise OCRError(str(exc)) from exc

        if source_lang not in {"ja", "zh", "auto"}:
            raise OCRError("`source_lang` must be `ja`, `zh`, or `auto`.")

        mode = self._resolve_ocr_engine(source_lang=source_lang, ocr_engine=ocr_engine)
        detection_mode = self._resolve_detection_engine(
            source_lang=source_lang,
            detection_engine=detection_engine,
        )
        paddle_lang = self._resolve_paddle_lang(source_lang)

        try:
            if mode == "gguf":
                blocks = self._detect_and_recognize(
                    image_array=image_array,
                    recognizer="gguf",
                    detection_engine=detection_mode,
                    paddle_lang=paddle_lang,
                )
                if not blocks:
                    blocks = self._recognize_with_gguf(image_array)
                return OCRResponse(image=ImageMeta(width=width, height=height), blocks=blocks)

            if mode == "hybrid":
                blocks = self._detect_and_recognize(
                    image_array=image_array,
                    recognizer="manga",
                    detection_engine=detection_mode,
                    paddle_lang=paddle_lang,
                )
                return OCRResponse(image=ImageMeta(width=width, height=height), blocks=blocks)

            if detection_mode == "bubble":
                blocks = self._detect_bubbles_with_paddle(
                    image_array=image_array,
                    paddle_lang=paddle_lang,
                )
                return OCRResponse(image=ImageMeta(width=width, height=height), blocks=blocks)

            raw_result = self._run_paddle_ocr(
                image_array,
                paddle_lang=paddle_lang,
                cls=True,
            )
        except Exception as exc:  # pragma: no cover - Paddle runtime errors vary
            raise OCRError(f"OCR processing failed: {exc}") from exc

        blocks = self._parse_full_result(raw_result)
        return OCRResponse(image=ImageMeta(width=width, height=height), blocks=blocks)

    def _resolve_ocr_engine(self, source_lang: str, ocr_engine: str) -> str:
        normalized = ocr_engine.strip().lower()
        if normalized not in {"auto", "gguf", "hybrid", "paddle"}:
            raise OCRError("`ocr_engine` must be `auto`, `gguf`, `hybrid`, or `paddle`.")

        if normalized == "auto":
            return "gguf" if source_lang == "ja" else "paddle"

        if normalized in {"gguf", "hybrid"} and source_lang != "ja":
            raise OCRError(f"`ocr_engine={normalized}` requires `source_lang=ja`.")

        return normalized

    def _resolve_detection_engine(self, source_lang: str, detection_engine: str) -> str:
        normalized = detection_engine.strip().lower()
        if normalized not in {"text", "bubble"}:
            raise OCRError("`detection_engine` must be `text` or `bubble`.")
        return normalized

    def _resolve_paddle_lang(self, source_lang: str) -> str:
        return "japan" if source_lang == "ja" else "ch"

    def _detect_and_recognize(
        self,
        image_array: Any,
        recognizer: str,
        detection_engine: str,
        paddle_lang: str,
    ) -> list[TextBlock]:
        if detection_engine == "bubble":
            return self._detect_bubbles_and_recognize(image_array, recognizer=recognizer, paddle_lang=paddle_lang)

        raw_result = self._run_paddle_ocr(
            image_array,
            paddle_lang=paddle_lang,
            det=True,
            rec=False,
            cls=True,
        )
        return self._parse_detection_result(image_array, raw_result, recognizer=recognizer)

    def _recognize_with_gguf(self, image_array: Any) -> list[TextBlock]:
        from PIL import Image

        rgb = cv2.cvtColor(image_array, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(rgb)
        text = self._normalize_japanese_text(self._gguf_ocr.recognize(image))
        height, width = image_array.shape[:2]
        bbox = [
            [0, 0],
            [width, 0],
            [width, height],
            [0, height],
        ]
        return [
            TextBlock(
                id=1,
                bbox=bbox,
                text=text,
                confidence=0.0,
                direction=infer_direction(bbox),
            )
        ]

    def _parse_full_result(
        self,
        raw_result: Any,
        offset_x: int = 0,
        offset_y: int = 0,
    ) -> list[TextBlock]:
        if not raw_result:
            return []

        first_page = raw_result[0] if isinstance(raw_result, list) else raw_result
        blocks: list[TextBlock] = []

        for index, line in enumerate(first_page or [], start=1):
            if not line or len(line) < 2:
                continue

            bbox_points, recognition = line[0], line[1]
            text = ""
            confidence = 0.0

            if isinstance(recognition, (list, tuple)) and recognition:
                text = str(recognition[0]) if len(recognition) > 0 else ""
                confidence = float(recognition[1]) if len(recognition) > 1 else 0.0

            bbox = normalize_bbox(bbox_points)
            if offset_x or offset_y:
                bbox = [[point[0] + offset_x, point[1] + offset_y] for point in bbox]
            blocks.append(
                TextBlock(
                    id=index,
                    bbox=bbox,
                    text=text.strip(),
                    confidence=round(confidence, 4),
                    direction=infer_direction(bbox),
                )
            )

        return blocks

    def _parse_detection_result(
        self,
        image_array: Any,
        raw_result: Any,
        recognizer: str = "manga",
    ) -> list[TextBlock]:
        if not raw_result:
            return []

        first_page = raw_result[0] if isinstance(raw_result, list) else raw_result
        raw_boxes: list[list[list[int]]] = []

        for item in first_page or []:
            bbox_points = item
            if (
                item
                and len(item) >= 2
                and isinstance(item[0], (list, tuple))
                and len(item[0]) == 2
                and isinstance(item[0][0], (int, float))
            ):
                bbox_points = item
            elif item and isinstance(item[0], (list, tuple)):
                bbox_points = item[0]
            raw_boxes.append(normalize_bbox(bbox_points))

        merged_groups = self._group_japanese_regions(raw_boxes)
        blocks: list[TextBlock] = []

        for index, group in enumerate(merged_groups, start=1):
            merged_bbox = union_bbox(group)

            try:
                text = self._recognize_group(
                    image_array=image_array,
                    group=group,
                    total_groups=len(merged_groups),
                    recognizer=recognizer,
                )
            except Exception as exc:
                raise OCRError(f"Japanese OCR failed on merged crop: {exc}") from exc

            blocks.append(
                TextBlock(
                    id=index,
                    bbox=merged_bbox,
                    text=text,
                    confidence=0.0,
                    direction=infer_direction(merged_bbox),
                )
            )

        return blocks

    def _detect_bubbles_and_recognize(
        self,
        image_array: Any,
        recognizer: str,
        paddle_lang: str,
    ) -> list[TextBlock]:
        bubble_polygons = self._bubble_detector.detect(image_array)
        if not bubble_polygons:
            return []

        blocks: list[TextBlock] = []
        next_id = 1

        for bubble_polygon in bubble_polygons:
            rect = rect_from_bbox(bubble_polygon)
            left, top, right, bottom = rect
            if right <= left or bottom <= top:
                continue

            bubble_crop = image_array[top:bottom, left:right]
            if bubble_crop.size == 0:
                continue

            raw_result = self._run_paddle_ocr(
                bubble_crop,
                paddle_lang=paddle_lang,
                det=True,
                rec=False,
                cls=True,
            )
            local_boxes = self._extract_detection_boxes(raw_result)
            shifted_boxes: list[list[list[int]]] = []
            for bbox in local_boxes:
                shifted = [[point[0] + left, point[1] + top] for point in bbox]
                if rect_intersection_area(rect_from_bbox(shifted), rect) > 0:
                    shifted_boxes.append(shifted)

            if not shifted_boxes:
                continue

            bubble_blocks = self._parse_detection_boxes(image_array, shifted_boxes, recognizer=recognizer)
            for block in bubble_blocks:
                block.id = next_id
                block.mask = bubble_polygon
                next_id += 1
            blocks.extend(bubble_blocks)

        return blocks

    def _detect_bubbles_with_paddle(
        self,
        image_array: Any,
        paddle_lang: str,
    ) -> list[TextBlock]:
        bubble_polygons = self._bubble_detector.detect(image_array)
        if not bubble_polygons:
            return []

        blocks: list[TextBlock] = []
        next_id = 1

        for bubble_polygon in bubble_polygons:
            left, top, right, bottom = rect_from_bbox(bubble_polygon)
            if right <= left or bottom <= top:
                continue

            bubble_crop = image_array[top:bottom, left:right]
            if bubble_crop.size == 0:
                continue

            raw_result = self._run_paddle_ocr(
                bubble_crop,
                paddle_lang=paddle_lang,
                cls=True,
            )
            bubble_blocks = self._parse_full_result(raw_result, offset_x=left, offset_y=top)
            for block in bubble_blocks:
                block.id = next_id
                block.mask = bubble_polygon
                next_id += 1
            blocks.extend(bubble_blocks)

        return blocks

    def _parse_detection_boxes(
        self,
        image_array: Any,
        raw_boxes: list[list[list[int]]],
        recognizer: str = "manga",
    ) -> list[TextBlock]:
        merged_groups = self._group_japanese_regions(raw_boxes)
        blocks: list[TextBlock] = []

        for index, group in enumerate(merged_groups, start=1):
            merged_bbox = union_bbox(group)
            try:
                text = self._recognize_group(
                    image_array=image_array,
                    group=group,
                    total_groups=len(merged_groups),
                    recognizer=recognizer,
                )
            except Exception as exc:
                raise OCRError(f"Japanese OCR failed on merged crop: {exc}") from exc

            blocks.append(
                TextBlock(
                    id=index,
                    bbox=merged_bbox,
                    text=text,
                    confidence=0.0,
                    direction=infer_direction(merged_bbox),
                )
            )

        return blocks

    def _extract_detection_boxes(self, raw_result: Any) -> list[list[list[int]]]:
        if not raw_result:
            return []

        first_page = raw_result[0] if isinstance(raw_result, list) else raw_result
        raw_boxes: list[list[list[int]]] = []

        for item in first_page or []:
            bbox_points = item
            if (
                item
                and len(item) >= 2
                and isinstance(item[0], (list, tuple))
                and len(item[0]) == 2
                and isinstance(item[0][0], (int, float))
            ):
                bbox_points = item
            elif item and isinstance(item[0], (list, tuple)):
                bbox_points = item[0]
            raw_boxes.append(normalize_bbox(bbox_points))

        return raw_boxes

    def _recognize_group(
        self,
        image_array: Any,
        group: list[list[list[int]]],
        total_groups: int,
        recognizer: str,
    ) -> str:
        if recognizer == "gguf":
            return self._recognize_gguf_group(image_array, group)
        return self._recognize_manga_group(image_array, group, total_groups)

    def _group_japanese_regions(self, bboxes: list[list[list[int]]]) -> list[list[list[list[int]]]]:
        if not bboxes:
            return []

        filtered = self._filter_nested_boxes(bboxes)
        rects = [rect_from_bbox(bbox) for bbox in filtered]
        _, median_height = median_rect_size(rects)
        vertical_bias = median_height >= 40
        parent = list(range(len(filtered)))

        def find(index: int) -> int:
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        def union(a: int, b: int) -> None:
            root_a = find(a)
            root_b = find(b)
            if root_a != root_b:
                parent[root_b] = root_a

        for i in range(len(filtered)):
            for j in range(i + 1, len(filtered)):
                if self._should_merge_regions(rects[i], rects[j], vertical_bias):
                    union(i, j)

        groups: dict[int, list[list[list[int]]]] = {}
        for index, bbox in enumerate(filtered):
            groups.setdefault(find(index), []).append(bbox)

        ordered_groups = self._merge_small_groups(list(groups.values()))
        ordered_groups.sort(key=self._group_sort_key, reverse=False)
        return ordered_groups

    def _filter_nested_boxes(self, bboxes: list[list[list[int]]]) -> list[list[list[int]]]:
        rects = [rect_from_bbox(bbox) for bbox in bboxes]
        keep = [True] * len(bboxes)

        for i, rect_i in enumerate(rects):
            area_i = rect_area(rect_i)
            if area_i == 0:
                keep[i] = False
                continue

            for j, rect_j in enumerate(rects):
                if i == j:
                    continue
                area_j = rect_area(rect_j)
                if area_j <= area_i:
                    continue

                intersection = rect_intersection_area(rect_i, rect_j)
                if intersection == 0:
                    continue

                overlap_ratio = intersection / area_i
                if (
                    rect_contains(rect_j, rect_i)
                    and overlap_ratio > self.config.nested_box_overlap_ratio
                    and area_i / area_j < self.config.nested_box_area_ratio
                ):
                    keep[i] = False
                    break

        return [bbox for bbox, include in zip(bboxes, keep) if include]

    def _should_merge_regions(
        self,
        rect_a: tuple[int, int, int, int],
        rect_b: tuple[int, int, int, int],
        vertical_bias: bool,
    ) -> bool:
        gap_x = rect_gap_x(rect_a, rect_b)
        gap_y = rect_gap_y(rect_a, rect_b)
        center_a = rect_center(rect_a)
        center_b = rect_center(rect_b)
        dx = abs(center_a[0] - center_b[0])
        dy = abs(center_a[1] - center_b[1])
        height_scale = max(rect_height(rect_a), rect_height(rect_b), 1)
        width_scale = max(rect_width(rect_a), rect_width(rect_b), 1)
        top_diff = abs(rect_a[1] - rect_b[1])
        bottom_diff = abs(rect_a[3] - rect_b[3])
        left_diff = abs(rect_a[0] - rect_b[0])
        right_diff = abs(rect_a[2] - rect_b[2])

        if rect_intersection_area(rect_a, rect_b) > 0:
            return True

        if vertical_bias:
            same_column = gap_x == 0 and gap_y <= height_scale * 0.45
            aligned_columns = (
                gap_x <= height_scale * 1.15
                and top_diff <= height_scale * 0.45
                and bottom_diff <= height_scale * 0.65
            )
            return same_column or aligned_columns

        same_row = gap_y == 0 and gap_x <= width_scale * 0.45
        aligned_rows = (
            gap_y <= width_scale * 1.15
            and left_diff <= width_scale * 0.45
            and right_diff <= width_scale * 0.65
        )
        return same_row or aligned_rows

    def _group_sort_key(self, group: list[list[list[int]]]) -> tuple[int, int]:
        merged = union_bbox(group)
        direction = infer_direction(merged)
        rect = rect_from_bbox(merged)
        if direction == "vertical":
            return (-rect[0], rect[1])
        return (rect[1], rect[0])

    def _normalize_japanese_text(self, text: str) -> str:
        normalized = unicodedata.normalize("NFKC", text.strip())
        normalized = normalized.replace("．．．", "...")
        normalized = normalized.replace("．．", "..")
        normalized = re.sub(r"([ぁ-んァ-ン一-龯])つ([.。…！!？?]+)", r"\1っ\2", normalized)
        normalized = normalized.replace("ことか", "とか")
        return normalized

    def _merge_small_groups(
        self,
        groups: list[list[list[list[int]]]],
    ) -> list[list[list[list[int]]]]:
        if len(groups) <= 1:
            return groups

        merged_rects = [rect_from_bbox(union_bbox(group)) for group in groups]
        areas = [rect_area(rect) for rect in merged_rects]
        max_area = max(areas) if areas else 0
        active = [list(group) for group in groups]

        for index, group in enumerate(groups):
            if not active[index] or max_area == 0:
                continue

            area_ratio = areas[index] / max_area
            if area_ratio >= self.config.small_group_area_ratio:
                continue

            nearest_index: int | None = None
            nearest_distance: float | None = None
            for other_index, other_group in enumerate(groups):
                if index == other_index or not active[other_index]:
                    continue

                gap_x = rect_gap_x(merged_rects[index], merged_rects[other_index])
                gap_y = rect_gap_y(merged_rects[index], merged_rects[other_index])
                distance = gap_x + gap_y
                if nearest_distance is None or distance < nearest_distance:
                    nearest_distance = distance
                    nearest_index = other_index

            if nearest_index is not None and nearest_distance is not None and nearest_distance <= max(
                rect_height(merged_rects[index]),
                rect_width(merged_rects[index]),
                40,
            ) * self.config.small_group_distance_scale:
                active[nearest_index].extend(active[index])
                active[index] = []

        return [group for group in active if group]

    def _recognize_manga_group(
        self,
        image_array: Any,
        group: list[list[list[int]]],
        total_groups: int,
    ) -> str:
        merged_bbox = union_bbox(group)
        candidates: list[tuple[str, float, str]] = []

        merged_crop = crop_polygon_region(
            image_array,
            merged_bbox,
            padding=self.config.region_crop_padding,
        )
        bubble_crop = crop_manga_bubble_region(
            image_array,
            merged_bbox,
            padding=self.config.region_crop_padding,
        )
        merged_text = self._normalize_japanese_text(self._manga_ocr.recognize(merged_crop))
        bubble_text = self._normalize_japanese_text(self._manga_ocr.recognize(bubble_crop))
        bubble_upscaled = bubble_crop.resize(
            (max(1, bubble_crop.width * 2), max(1, bubble_crop.height * 2)),
            resample=1,
        )
        bubble_upscaled_text = self._normalize_japanese_text(self._manga_ocr.recognize(bubble_upscaled))
        bubble_threshold = ImageOps.autocontrast(ImageOps.grayscale(bubble_crop), cutoff=1)
        bubble_threshold_text = self._normalize_japanese_text(self._manga_ocr.recognize(bubble_threshold))
        for text in [merged_text, bubble_text, bubble_upscaled_text, bubble_threshold_text]:
            if text:
                candidates.append((text, 0.0, "manga"))

        paddle_merged_text, paddle_merged_conf = self._recognize_with_paddle_crop(merged_crop)
        if paddle_merged_text:
            candidates.append((self._normalize_japanese_text(paddle_merged_text), paddle_merged_conf, "paddle"))

        paddle_bubble_text, paddle_bubble_conf = self._recognize_with_paddle_crop(bubble_crop)
        if paddle_bubble_text:
            candidates.append((self._normalize_japanese_text(paddle_bubble_text), paddle_bubble_conf, "paddle"))

        best_text = max(candidates, key=lambda item: self._score_candidate(item[0], item[1], item[2]), default=("", 0.0, ""))[0]

        ordered_boxes = self._sort_group_boxes(group)
        if len(ordered_boxes) > 1 and len(merged_text) < max(10, len(group) * 2):
            line_texts: list[str] = []
            for bbox in ordered_boxes:
                line_crop = crop_polygon_region(
                    image_array,
                    bbox,
                    padding=self.config.line_crop_padding,
                )
                line_text = self._normalize_japanese_text(self._manga_ocr.recognize(line_crop))
                if line_text:
                    line_texts.append(line_text)
            if line_texts:
                candidates.append(("".join(line_texts), 0.0, "manga-lines"))

        if total_groups == 1 and self._covers_most_of_image(image_array, merged_bbox):
            whole_bbox = [
                [0, 0],
                [image_array.shape[1], 0],
                [image_array.shape[1], image_array.shape[0]],
                [0, image_array.shape[0]],
            ]
            whole_crop = crop_polygon_region(image_array, whole_bbox, padding=0)
            whole_text = self._normalize_japanese_text(self._manga_ocr.recognize(whole_crop))
            if self._prefer_whole_image_text(whole_text, merged_text):
                best_text = whole_text

        candidates.append((best_text, 0.0, "best"))

        ranked = [candidate for candidate in candidates if candidate[0]]
        if not ranked:
            return ""
        return max(ranked, key=lambda item: self._score_candidate(item[0], item[1], item[2]))[0]

    def _recognize_gguf_group(
        self,
        image_array: Any,
        group: list[list[list[int]]],
    ) -> str:
        merged_bbox = union_bbox(group)
        candidates: list[tuple[str, float, str]] = []

        merged_crop = crop_polygon_region(
            image_array,
            merged_bbox,
            padding=self.config.region_crop_padding,
        )
        bubble_crop = crop_manga_bubble_region(
            image_array,
            merged_bbox,
            padding=self.config.region_crop_padding,
        )

        for crop, source in ((merged_crop, "gguf-merged"), (bubble_crop, "gguf-bubble")):
            text = self._normalize_japanese_text(self._gguf_ocr.recognize(crop))
            if text:
                candidates.append((text, 0.0, source))

        if not candidates:
            return ""

        return max(candidates, key=lambda item: self._score_candidate(item[0], item[1], item[2]))[0]

    def _sort_group_boxes(self, group: list[list[list[int]]]) -> list[list[list[int]]]:
        merged_bbox = union_bbox(group)
        direction = infer_direction(merged_bbox)
        if direction == "vertical":
            return sorted(group, key=lambda bbox: (-rect_from_bbox(bbox)[0], rect_from_bbox(bbox)[1]))
        return sorted(group, key=lambda bbox: (rect_from_bbox(bbox)[1], rect_from_bbox(bbox)[0]))

    def _covers_most_of_image(self, image_array: Any, merged_bbox: list[list[int]]) -> bool:
        image_area = image_array.shape[0] * image_array.shape[1]
        if image_area <= 0:
            return False
        return rect_area(rect_from_bbox(merged_bbox)) / image_area >= self.config.whole_image_coverage_threshold


    def _score_manga_candidate(self, text: str) -> tuple[int, int, int]:
        stripped = text.strip()
        japanese_count = self._count_japanese_chars(stripped)
        punctuation_penalty = sum(1 for char in stripped if char in {"?", "？", "-", "—"})
        return (japanese_count, len(stripped) - punctuation_penalty, len(stripped))

    def _score_candidate(self, text: str, confidence: float, source: str) -> tuple[float, float, float, float]:
        stripped = text.strip()
        japanese_count = self._count_japanese_chars(stripped)
        latin_count = sum(1 for char in stripped if re.match(r"[A-Za-z0-9]", char))
        quote_count = sum(1 for char in stripped if char in {"「", "」", "『", "』", "(", ")", "!", "！", "?", "？"})
        bad_symbol_penalty = sum(1 for char in stripped if char in {"~", "_", "…", "・"} and len(stripped) > 4)
        source_bonus = 0.15 if source == "manga" else 0.0
        confidence_bonus = confidence if source == "paddle" else 0.0
        content_score = japanese_count + (latin_count * 0.7) + (quote_count * 0.2) - (bad_symbol_penalty * 0.8)
        length_score = len(stripped) * 0.05
        return (content_score + source_bonus + confidence_bonus, content_score, length_score, len(stripped))

    def _count_japanese_chars(self, text: str) -> int:
        return sum(1 for char in text if re.match(r"[ぁ-んァ-ン一-龯々ー]", char))

    def _recognize_with_paddle_crop(self, crop_image: Any, paddle_lang: str = "japan") -> tuple[str, float]:
        try:
            bgr = cv2.cvtColor(np.array(crop_image), cv2.COLOR_RGB2BGR)
            result = self._run_paddle_ocr(bgr, paddle_lang=paddle_lang, det=False, rec=True, cls=False)
        except Exception:
            return ("", 0.0)

        if not result or not isinstance(result, list) or not result[0]:
            return ("", 0.0)

        first = result[0][0]
        if not isinstance(first, (list, tuple)) or len(first) < 2:
            return ("", 0.0)

        text = str(first[0]).strip()
        confidence = float(first[1]) if len(first) > 1 else 0.0
        return (text, confidence)

    def _prefer_whole_image_text(self, whole_text: str, merged_text: str) -> bool:
        if not whole_text:
            return False
        if not merged_text:
            return True
        whole_score = self._score_manga_candidate(whole_text)
        merged_score = self._score_manga_candidate(merged_text)
        if whole_score[0] >= merged_score[0] and whole_score[1] >= merged_score[1]:
            return True
        return len(whole_text) >= len(merged_text) + 6

    def _run_paddle_ocr(self, image: Any, paddle_lang: str = "japan", **kwargs: Any) -> Any:
        ocr = self._get_instance(paddle_lang)
        try:
            return ocr.ocr(image, **kwargs)
        except Exception as exc:
            if not self._should_reset_paddle(exc):
                raise
            self._ocr_instances.pop(paddle_lang, None)
            return self._get_instance(paddle_lang).ocr(image, **kwargs)

    def _should_reset_paddle(self, exc: Exception) -> bool:
        message = str(exc).lower()
        return "primitive" in message or "onednn" in message or "mkldnn" in message
