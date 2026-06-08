from __future__ import annotations

from dataclasses import dataclass

from backend.schemas.block import TextBlock, TextGroup


@dataclass
class GroupedPage:
    groups: list[TextGroup]


def build_text_groups(blocks: list[TextBlock]) -> GroupedPage:
    if not blocks:
        return GroupedPage(groups=[])

    ordered_blocks = sorted(blocks, key=_block_sort_key)
    groups: list[TextGroup] = []
    used: set[int] = set()

    for block in ordered_blocks:
        if block.id in used:
            continue

        cluster = [block]
        used.add(block.id)

        for candidate in ordered_blocks:
            if candidate.id in used:
                continue
            if _should_join_group(cluster, candidate):
                cluster.append(candidate)
                used.add(candidate.id)

        cluster.sort(key=_block_sort_key)
        groups.append(_group_from_blocks(len(groups) + 1, cluster))

    groups.sort(key=_group_sort_key)
    for index, group in enumerate(groups, start=1):
        group.id = index
        group.reading_order = index

    return GroupedPage(groups=groups)


def _group_from_blocks(group_id: int, blocks: list[TextBlock]) -> TextGroup:
    xs = [point[0] for block in blocks for point in block.bbox]
    ys = [point[1] for block in blocks for point in block.bbox]
    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)
    bbox = [
        [min_x, min_y],
        [max_x, min_y],
        [max_x, max_y],
        [min_x, max_y],
    ]
    combined_text = "\n".join(block.text.strip() for block in blocks if block.text.strip())
    mask = _select_group_mask(blocks)

    return TextGroup(
        id=group_id,
        block_ids=[block.id for block in blocks],
        bbox=bbox,
        mask=mask,
        x=min_x,
        y=min_y,
        width=max_x - min_x,
        height=max_y - min_y,
        reading_order=group_id,
        source_text=combined_text,
        corrected_text=combined_text,
        translated_text="",
    )


def _select_group_mask(blocks: list[TextBlock]) -> list[list[int]]:
    masks = [block.mask for block in blocks if getattr(block, "mask", None)]
    if not masks:
        return []
    return max(masks, key=_polygon_area)


def _polygon_area(polygon: list[list[int]]) -> int:
    if len(polygon) < 3:
        return 0
    area = 0
    for index, point in enumerate(polygon):
        next_point = polygon[(index + 1) % len(polygon)]
        area += point[0] * next_point[1] - next_point[0] * point[1]
    return abs(area) // 2


def _block_sort_key(block: TextBlock) -> tuple[int, int]:
    left, top, right, bottom = _rect_from_bbox(block.bbox)
    height = bottom - top
    width = right - left
    if height >= width:
        return (-left, top)
    return (top, left)


def _group_sort_key(group: TextGroup) -> tuple[int, int]:
    left, top, right, bottom = _rect_from_bbox(group.bbox)
    height = bottom - top
    width = right - left
    if height >= width:
        return (-left, top)
    return (top, left)


def _should_join_group(cluster: list[TextBlock], candidate: TextBlock) -> bool:
    candidate_rect = _rect_from_bbox(candidate.bbox)
    cluster_rects = [_rect_from_bbox(block.bbox) for block in cluster]

    if not any(_rects_are_neighbors(cluster_rect, candidate_rect) for cluster_rect in cluster_rects):
        return False

    cluster_bbox = _union_bbox([block.bbox for block in cluster])
    proposed_bbox = _union_bbox([cluster_bbox, candidate.bbox])
    proposed_rect = _rect_from_bbox(proposed_bbox)
    proposed_area = max(_rect_area(proposed_rect), 1)
    covered_area = sum(_rect_area(cluster_rect) for cluster_rect in cluster_rects) + _rect_area(candidate_rect)
    coverage_ratio = covered_area / proposed_area
    return coverage_ratio >= 0.38


def _rects_are_neighbors(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    width_a = max(a[2] - a[0], 1)
    height_a = max(a[3] - a[1], 1)
    width_b = max(b[2] - b[0], 1)
    height_b = max(b[3] - b[1], 1)
    vertical_bias = (height_a + height_b) >= (width_a + width_b)

    gap_x = _rect_gap_x(a, b)
    gap_y = _rect_gap_y(a, b)
    overlap_x = _rect_overlap_x(a, b)
    overlap_y = _rect_overlap_y(a, b)

    if vertical_bias:
        same_column = gap_x == 0 and gap_y <= min(height_a, height_b) * 0.35
        nearby_columns = gap_x <= max(width_a, width_b) * 0.75 and overlap_y >= min(height_a, height_b) * 0.35
        return same_column or nearby_columns

    same_row = gap_y == 0 and gap_x <= min(width_a, width_b) * 0.35
    nearby_rows = gap_y <= max(height_a, height_b) * 0.75 and overlap_x >= min(width_a, width_b) * 0.35
    return same_row or nearby_rows


def _union_bbox(bboxes: list[list[list[int]]]) -> list[list[int]]:
    xs = [point[0] for bbox in bboxes for point in bbox]
    ys = [point[1] for bbox in bboxes for point in bbox]
    return [
        [min(xs), min(ys)],
        [max(xs), min(ys)],
        [max(xs), max(ys)],
        [min(xs), max(ys)],
    ]


def _rect_from_bbox(bbox: list[list[int]]) -> tuple[int, int, int, int]:
    xs = [point[0] for point in bbox]
    ys = [point[1] for point in bbox]
    return min(xs), min(ys), max(xs), max(ys)


def _rect_area(rect: tuple[int, int, int, int]) -> int:
    return max(0, rect[2] - rect[0]) * max(0, rect[3] - rect[1])


def _rect_gap_x(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> int:
    if a[2] < b[0]:
        return b[0] - a[2]
    if b[2] < a[0]:
        return a[0] - b[2]
    return 0


def _rect_gap_y(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> int:
    if a[3] < b[1]:
        return b[1] - a[3]
    if b[3] < a[1]:
        return a[1] - b[3]
    return 0


def _rect_overlap_x(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> int:
    return max(0, min(a[2], b[2]) - max(a[0], b[0]))


def _rect_overlap_y(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> int:
    return max(0, min(a[3], b[3]) - max(a[1], b[1]))
