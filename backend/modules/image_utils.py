from __future__ import annotations

from io import BytesIO
from statistics import median

import cv2
import numpy as np
from PIL import Image


def load_image_from_bytes(image_bytes: bytes) -> tuple[np.ndarray, int, int]:
    try:
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
    except Exception as exc:  # pragma: no cover - pillow exception types vary
        raise ValueError("Could not decode the uploaded image.") from exc

    width, height = image.size
    rgb_array = np.array(image)
    bgr_array = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR)
    return bgr_array, width, height


def normalize_bbox(points: list[list[float]] | list[tuple[float, float]]) -> list[list[int]]:
    normalized: list[list[int]] = []
    for point in points:
        x, y = point
        normalized.append([int(round(x)), int(round(y))])
    return normalized


def infer_direction(bbox: list[list[int]]) -> str:
    if len(bbox) < 4:
        return "horizontal"

    width = ((bbox[1][0] - bbox[0][0]) ** 2 + (bbox[1][1] - bbox[0][1]) ** 2) ** 0.5
    height = ((bbox[3][0] - bbox[0][0]) ** 2 + (bbox[3][1] - bbox[0][1]) ** 2) ** 0.5
    return "vertical" if height > width else "horizontal"


def crop_polygon_region(
    image_bgr: np.ndarray,
    bbox: list[list[int]],
    padding: int = 8,
) -> Image.Image:
    if not bbox:
        raise ValueError("Cannot crop an empty bounding box.")

    xs = [point[0] for point in bbox]
    ys = [point[1] for point in bbox]
    height, width = image_bgr.shape[:2]

    left = max(min(xs) - padding, 0)
    top = max(min(ys) - padding, 0)
    right = min(max(xs) + padding, width)
    bottom = min(max(ys) + padding, height)

    cropped = image_bgr[top:bottom, left:right]
    if cropped.size == 0:
        raise ValueError("Bounding box crop is empty.")

    rgb = cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


def crop_manga_bubble_region(
    image_bgr: np.ndarray,
    bbox: list[list[int]],
    padding: int = 20,
    search_margin: int = 48,
    white_threshold: int = 200,
) -> Image.Image:
    if not bbox:
        raise ValueError("Cannot crop an empty bounding box.")

    xs = [point[0] for point in bbox]
    ys = [point[1] for point in bbox]
    image_height, image_width = image_bgr.shape[:2]

    left = max(min(xs) - search_margin, 0)
    top = max(min(ys) - search_margin, 0)
    right = min(max(xs) + search_margin, image_width)
    bottom = min(max(ys) + search_margin, image_height)

    window = image_bgr[top:bottom, left:right]
    if window.size == 0:
        return crop_polygon_region(image_bgr, bbox, padding=padding)

    gray = cv2.cvtColor(window, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, white_threshold, 255, cv2.THRESH_BINARY)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(closed)
    local_rect = (
        min(xs) - left,
        min(ys) - top,
        max(xs) - left,
        max(ys) - top,
    )
    center_x = int((local_rect[0] + local_rect[2]) / 2)
    center_y = int((local_rect[1] + local_rect[3]) / 2)
    bbox_area = max(1, (local_rect[2] - local_rect[0]) * (local_rect[3] - local_rect[1]))

    best_label = 0
    best_overlap = 0
    for label in range(1, num_labels):
        x = stats[label, cv2.CC_STAT_LEFT]
        y = stats[label, cv2.CC_STAT_TOP]
        w = stats[label, cv2.CC_STAT_WIDTH]
        h = stats[label, cv2.CC_STAT_HEIGHT]
        area = stats[label, cv2.CC_STAT_AREA]
        if area <= 0:
            continue

        contains_center = x <= center_x < x + w and y <= center_y < y + h
        overlap_left = max(x, local_rect[0])
        overlap_top = max(y, local_rect[1])
        overlap_right = min(x + w, local_rect[2])
        overlap_bottom = min(y + h, local_rect[3])
        overlap = max(0, overlap_right - overlap_left) * max(0, overlap_bottom - overlap_top)

        if contains_center and overlap >= best_overlap:
            best_label = label
            best_overlap = overlap
        elif overlap > best_overlap and area >= bbox_area:
            best_label = label
            best_overlap = overlap

    if best_label == 0:
        return crop_polygon_region(image_bgr, bbox, padding=padding)

    x = stats[best_label, cv2.CC_STAT_LEFT]
    y = stats[best_label, cv2.CC_STAT_TOP]
    w = stats[best_label, cv2.CC_STAT_WIDTH]
    h = stats[best_label, cv2.CC_STAT_HEIGHT]

    expanded_left = max(left + x - padding, 0)
    expanded_top = max(top + y - padding, 0)
    expanded_right = min(left + x + w + padding, image_width)
    expanded_bottom = min(top + y + h + padding, image_height)

    cropped = image_bgr[expanded_top:expanded_bottom, expanded_left:expanded_right]
    if cropped.size == 0:
        return crop_polygon_region(image_bgr, bbox, padding=padding)

    rgb = cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


def rect_from_bbox(bbox: list[list[int]]) -> tuple[int, int, int, int]:
    xs = [point[0] for point in bbox]
    ys = [point[1] for point in bbox]
    return min(xs), min(ys), max(xs), max(ys)


def rect_width(rect: tuple[int, int, int, int]) -> int:
    return max(0, rect[2] - rect[0])


def rect_height(rect: tuple[int, int, int, int]) -> int:
    return max(0, rect[3] - rect[1])


def rect_area(rect: tuple[int, int, int, int]) -> int:
    return rect_width(rect) * rect_height(rect)


def rect_intersection_area(
    a: tuple[int, int, int, int],
    b: tuple[int, int, int, int],
) -> int:
    left = max(a[0], b[0])
    top = max(a[1], b[1])
    right = min(a[2], b[2])
    bottom = min(a[3], b[3])
    if right <= left or bottom <= top:
        return 0
    return (right - left) * (bottom - top)


def rect_contains(
    outer: tuple[int, int, int, int],
    inner: tuple[int, int, int, int],
    tolerance: int = 4,
) -> bool:
    return (
        inner[0] >= outer[0] - tolerance
        and inner[1] >= outer[1] - tolerance
        and inner[2] <= outer[2] + tolerance
        and inner[3] <= outer[3] + tolerance
    )


def union_bbox(bboxes: list[list[list[int]]]) -> list[list[int]]:
    xs: list[int] = []
    ys: list[int] = []
    for bbox in bboxes:
        for x, y in bbox:
            xs.append(x)
            ys.append(y)
    return [
        [min(xs), min(ys)],
        [max(xs), min(ys)],
        [max(xs), max(ys)],
        [min(xs), max(ys)],
    ]


def rect_center(rect: tuple[int, int, int, int]) -> tuple[float, float]:
    return ((rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2)


def rect_gap_x(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> int:
    if a[2] < b[0]:
        return b[0] - a[2]
    if b[2] < a[0]:
        return a[0] - b[2]
    return 0


def rect_gap_y(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> int:
    if a[3] < b[1]:
        return b[1] - a[3]
    if b[3] < a[1]:
        return a[1] - b[3]
    return 0


def median_rect_size(rects: list[tuple[int, int, int, int]]) -> tuple[float, float]:
    if not rects:
        return (0.0, 0.0)
    widths = [rect_width(rect) for rect in rects]
    heights = [rect_height(rect) for rect in rects]
    return median(widths), median(heights)
