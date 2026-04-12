"""
IoU evaluator — computes Intersection over Union between A11Y and VLM bboxes.

A11Y bbox is the ground truth; VLM bbox is the prediction.
Bboxes are in [x, y, w, h] format (origin = top-left, absolute pixels).
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from src.domain.models import IoURecord, LocatorResult

# Re-use pure math functions from existing Phase 1 code
from src.exploration.evaluate_iou import bbox_area, intersection_area, bbox_center

logger = logging.getLogger(__name__)

# Internal BBox type: (x1, y1, x2, y2)
_BBox = Tuple[float, float, float, float]


def _xywh_to_xyxy(bbox: List[float]) -> _BBox:
    """Convert [x, y, w, h] → (x1, y1, x2, y2)."""
    x, y, w, h = bbox
    return x, y, x + w, y + h


def compute_iou(a11y_result: LocatorResult, vlm_result: LocatorResult) -> IoURecord:
    """
    Compute IoU between A11Y (ground truth) and VLM (prediction) bboxes.

    Returns an IoURecord regardless of whether both locators found the element.
    """
    a11y_bbox_raw = a11y_result.bbox if a11y_result.found else None
    vlm_bbox_raw = vlm_result.bbox if vlm_result.found else None

    if a11y_bbox_raw is None or vlm_bbox_raw is None:
        return IoURecord(
            a11y_bbox=a11y_bbox_raw,
            vlm_bbox=vlm_bbox_raw,
            iou_score=None,
            center_error_px=None,
        )

    a = _xywh_to_xyxy(a11y_bbox_raw)
    b = _xywh_to_xyxy(vlm_bbox_raw)

    inter = intersection_area(a, b)
    union = bbox_area(a) + bbox_area(b) - inter
    iou_score = inter / union if union > 0 else 0.0

    ax, ay = bbox_center(a)
    bx, by = bbox_center(b)
    center_err = ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5

    logger.debug(
        "IoU: a11y=%s vlm=%s → iou=%.4f center_err=%.1fpx",
        a11y_bbox_raw, vlm_bbox_raw, iou_score, center_err,
    )

    return IoURecord(
        a11y_bbox=a11y_bbox_raw,
        vlm_bbox=vlm_bbox_raw,
        iou_score=round(iou_score, 4),
        center_error_px=round(center_err, 2),
    )
