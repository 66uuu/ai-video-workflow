# -*- coding: utf-8 -*-
"""工作流项目路径解析。

把旧脚本里散落的 EP04、E 盘和仓库内产出路径统一收口，允许每个项目
通过环境变量或命令行覆盖。这个文件只负责路径，不负责创建或删除文件。
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional


SCRIPT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_PARENT = Path(
    os.environ.get("NR_OUTPUT_PARENT", r"你的桌面\AI产物")
)


def _first_existing(candidates: Iterable[Path]) -> Optional[Path]:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


class ProjectPaths:
    """解析一套镜头项目的输入、视频、日志和交付路径。"""

    def __init__(
        self,
        project_root: Optional[str] = None,
        episode: Optional[str] = None,
        timeline: Optional[str] = None,
        shots: Optional[str] = None,
        video_dir: Optional[str] = None,
        lock_dir: Optional[str] = None,
        log_dir: Optional[str] = None,
        output_dir: Optional[str] = None,
    ) -> None:
        root_value = project_root or os.environ.get("NR_PROJECT_ROOT") or str(SCRIPT_ROOT)
        self.root = Path(root_value).expanduser().resolve()
        self.episode = (episode or os.environ.get("NR_EPISODE") or "EP04").upper()

        self.timeline = self._resolve_file(
            timeline or os.environ.get("NR_TIMELINE"),
            [
                self.root / "06_分镜与时间轴" / f"{self.episode}_timeline_v2.json",
                self.root / f"{self.episode}_timeline_v2.json",
            ],
        )
        self.shots = self._resolve_file(
            shots or os.environ.get("NR_SHOTS"),
            [
                self.root / "06_分镜与时间轴" / f"SHOTS_{self.episode}.json",
                self.root / f"SHOTS_{self.episode}.json",
            ],
        )

        self.asset_root = self.root / "08_资产库"
        self.lock_dir = Path(lock_dir or os.environ.get("NR_LOCK_DIR") or self._default_lock_dir())

        self.output_dir = self._resolve_output_dir(output_dir)
        self.video_dir = Path(
            video_dir
            or os.environ.get("NR_VIDEO_DIR")
            or self._default_video_dir()
        )
        self.log_dir = Path(
            log_dir
            or os.environ.get("NR_LOG_DIR")
            or self._default_log_dir()
        )
        self.input_subdir = os.environ.get("NR_INPUT_SUBDIR", "NR_I2V")

    def _resolve_file(self, explicit: Optional[str], fallbacks: list[Path]) -> Path:
        if explicit:
            return Path(explicit).expanduser().resolve()
        return _first_existing(fallbacks) or fallbacks[0]

    def _default_lock_dir(self) -> Path:
        candidates = [
            self.asset_root / "_资产锁定",
            self.asset_root / f"{self.episode}_关键帧",
            self.asset_root,
        ]
        return _first_existing(candidates) or candidates[0]

    def _resolve_output_dir(self, explicit: Optional[str]) -> Path:
        if explicit or os.environ.get("NR_OUTPUT_DIR"):
            return Path(explicit or os.environ["NR_OUTPUT_DIR"]).expanduser().resolve()

        # 技能包本身不是成品目录；默认把成品放到 你的桌面\AI产物。
        if self.root == SCRIPT_ROOT:
            stamp = datetime.now().strftime("%Y%m%d")
            return DEFAULT_OUTPUT_PARENT / f"{stamp}_{self.episode}"
        return self.root / "成片"

    def _default_video_dir(self) -> Path:
        candidates = [
            self.root / "视频",
            self.root / "video_i2v",
            self.root / "05_成品视频" / "单镜原片",
        ]
        if self.root == SCRIPT_ROOT:
            return self.output_dir / "视频"
        return _first_existing(candidates) or candidates[0]

    def _default_log_dir(self) -> Path:
        candidates = [self.root / "日志", self.root / "_logs"]
        if self.root == SCRIPT_ROOT:
            return self.output_dir / "日志"
        return _first_existing(candidates) or candidates[0]

    def resolve_asset(self, value: str) -> Path:
        """解析镜头 JSON 中的图片路径，并兼容旧版相对路径。"""
        raw = Path(str(value))
        if raw.is_absolute():
            return raw
        candidates = [
            self.root / raw,
            self.asset_root / raw,
            self.lock_dir / raw,
            self.asset_root / f"{self.episode}_关键帧" / raw.name,
            self.asset_root / "_资产锁定" / raw,
            self.asset_root / "_资产锁定" / raw.name,
        ]
        return _first_existing(candidates) or candidates[0]

    @property
    def submit_log(self) -> Path:
        return self.video_dir / "_submitted.json"

    @property
    def rework_json(self) -> Path:
        return self.video_dir / "重做清单.json"

    @property
    def rework_md(self) -> Path:
        return self.video_dir / "重做清单.md"

    def as_strings(self) -> dict[str, str]:
        return {
            "root": str(self.root),
            "episode": self.episode,
            "timeline": str(self.timeline),
            "shots": str(self.shots),
            "lock_dir": str(self.lock_dir),
            "video_dir": str(self.video_dir),
            "log_dir": str(self.log_dir),
            "output_dir": str(self.output_dir),
        }
