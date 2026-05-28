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

    return TextGroup(
        id=group_id,
        block_ids=[block.id for block in blocks],
        bbox=bbox,
        x=min_x,
        y=min_y,
        width=max_x - min_x,
        height=max_y - min_y,
        reading_order=group_id,
        source_text=combined_text,
        corrected_text=combined_text,
        translated_text="",
    )


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
    cluster_bbox = _union_bbox([block.bbox for block in cluster])
    candidate_rect = _rect_from_bbox(candidate.bbox)
    cluster_rect = _rect_from_bbox(cluster_bbox)
    cluster_height = max(cluster_rect[3] - cluster_rect[1], 1)
    cluster_width = max(cluster_rect[2] - cluster_rect[0], 1)
    candidate_height = max(candidate_rect[3] - candidate_rect[1], 1)
    candidate_width = max(candidate_rect[2] - candidate_rect[0], 1)

    vertical_bias = cluster_height >= cluster_width
    if vertical_bias:
        gap_x = _rect_gap_x(cluster_rect, candidate_rect)
        overlap_y = _rect_overlap_y(cluster_rect, candidate_rect)
        return gap_x <= max(cluster_width, candidate_width) * 1.1 and overlap_y >= min(cluster_height, candidate_height) * 0.18

    gap_y = _rect_gap_y(cluster_rect, candidate_rect)
    overlap_x = _rect_overlap_x(cluster_rect, candidate_rect)
    return gap_y <= max(cluster_height, candidate_height) * 1.1 and overlap_x >= min(cluster_width, candidate_width) * 0.18


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
