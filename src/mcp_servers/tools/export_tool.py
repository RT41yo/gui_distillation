"""
MCP-style export tools: DART episode bundle and summary.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.domain.models import EpisodeRecord
from src.exporters.dart_exporter import DartExporter
from src.exporters.summary_exporter import SummaryExporter


@dataclass
class ExportDartEpisodeInput:
    episode: EpisodeRecord
    dart_root: Path
    internal_episode_dir: Path


@dataclass
class ExportDartEpisodeOutput:
    episode_bundle_dir: Path


class ExportDartEpisodeTool:
    """Convert an internal EpisodeRecord into a DART-like bundle on disk."""

    def __init__(self, exporter: DartExporter) -> None:
        self._exporter = exporter

    def run(self, inp: ExportDartEpisodeInput) -> ExportDartEpisodeOutput:
        bundle_dir = self._exporter.export(
            episode=inp.episode,
            dart_root=inp.dart_root,
            internal_episode_dir=inp.internal_episode_dir,
        )
        return ExportDartEpisodeOutput(episode_bundle_dir=bundle_dir)


# ---------------------------------------------------------------------------

@dataclass
class ExportDartSummaryInput:
    dart_root: Path


class ExportDartSummaryTool:
    """Rebuild all_result.json and summary/results.json from exported bundles."""

    def __init__(self, exporter: SummaryExporter) -> None:
        self._exporter = exporter

    def run(self, inp: ExportDartSummaryInput) -> None:
        self._exporter.export(inp.dart_root)
