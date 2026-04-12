"""
dHash evaluator — computes perceptual hash and Hamming distance per step,
and builds a per-episode Hamming distance bar chart.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from src.domain.models import DHashRecord

logger = logging.getLogger(__name__)


def _hamming_distance(hash1: Optional[str], hash2: Optional[str]) -> Optional[int]:
    """Compute Hamming distance between two dHash hex strings."""
    if not hash1 or not hash2:
        return None
    try:
        return bin(int(hash1, 16) ^ int(hash2, 16)).count("1")
    except ValueError:
        return None


def compute_dhash_record(
    before_path: Optional[Path],
    after_path: Optional[Path],
    dhash_size: int = 8,
) -> DHashRecord:
    """
    Compute dHash for before/after screenshots and their Hamming distance.
    """
    before_hash: Optional[str] = None
    after_hash: Optional[str] = None

    if before_path and before_path.exists():
        before_hash = _dhash(before_path, dhash_size)
    if after_path and after_path.exists():
        after_hash = _dhash(after_path, dhash_size)

    hamming = _hamming_distance(before_hash, after_hash)

    return DHashRecord(
        before_dhash=before_hash,
        after_dhash=after_hash,
        hamming_distance=hamming,
    )


def _dhash(path: Path, size: int) -> str:
    """Compute dHash hex string for an image file."""
    try:
        from PIL import Image
    except ImportError as e:
        raise RuntimeError("Pillow is required for dHash computation") from e

    with Image.open(path) as raw:
        img = raw.convert("L").resize((size + 1, size))
    pixels = list(img.tobytes())
    bits: List[int] = []
    for y in range(size):
        row = y * (size + 1)
        for x in range(size):
            bits.append(1 if pixels[row + x] > pixels[row + x + 1] else 0)
    value = 0
    for b in bits:
        value = (value << 1) | b
    width = (size * size + 3) // 4
    return f"{value:0{width}x}"


def plot_hamming_chart(
    hamming_distances: List[Optional[int]],
    output_path: Path,
    title: str = "Hamming Distance per Step",
) -> None:
    """
    Save a bar chart of Hamming distances across steps.

    Each bar represents one step; height = Hamming distance between
    before/after screenshots for that step.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning("matplotlib not available — skipping Hamming chart")
        return

    steps = list(range(len(hamming_distances)))
    values = [d if d is not None else 0 for d in hamming_distances]

    fig, ax = plt.subplots(figsize=(max(6, len(steps) * 0.5), 4))
    ax.bar(steps, values, color="steelblue")
    ax.set_xlabel("Step")
    ax.set_ylabel("Hamming Distance")
    ax.set_title(title)
    ax.set_xticks(steps)
    ax.set_xticklabels([str(s) for s in steps], rotation=45, ha="right")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=100)
    plt.close(fig)
    logger.info("Hamming chart saved → %s", output_path)
