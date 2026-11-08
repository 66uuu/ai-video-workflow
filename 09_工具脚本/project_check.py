# -*- coding: utf-8 -*-
"""生成前自检：把缺首帧、模型名、ComfyUI 路径和质检依赖一次说清楚。"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from project_paths import ProjectPaths


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-root", default=os.environ.get("NR_PROJECT_ROOT", ""))
    ap.add_argument("--episode", default=os.environ.get("NR_EPISODE", ""))
    ap.add_argument("--timeline", default=os.environ.get("NR_TIMELINE", ""))
    ap.add_argument("--shots", default=os.environ.get("NR_SHOTS", ""))
    ap.add_argument("--video-dir", default=os.environ.get("NR_VIDEO_DIR", ""))
    ap.add_argument("--lock-dir", default=os.environ.get("NR_LOCK_DIR", ""))
    ap.add_argument("--json", action="store_true", help="输出机器可读结果")
    a = ap.parse_args()

    p = ProjectPaths(
        project_root=a.project_root, episode=a.episode, timeline=a.timeline,
        shots=a.shots, video_dir=a.video_dir, lock_dir=a.lock_dir,
    )
    result = {
        "ok": True,
        "project": p.as_strings(),
        "checks": [],
    }

    def check(name: str, ok: bool, detail: str) -> None:
        result["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
        if not ok:
            result["ok"] = False

    check("时间轴", p.timeline.exists(), str(p.timeline))
    check("镜头包", p.shots.exists(), str(p.shots))
    check("ComfyUI", Path(os.environ.get("COMFY_ROOT", r"ComfyUI")).exists(),
          os.environ.get("COMFY_ROOT", r"ComfyUI"))
    check("ffmpeg", bool(os.environ.get("FFMPEG") or shutil.which("ffmpeg") or
                         Path(r"ComfyUI\ffmpeg.exe").exists()),
          os.environ.get("FFMPEG") or shutil.which("ffmpeg") or r"ComfyUI\ffmpeg.exe")

    if p.timeline.exists():
        try:
            timeline = json.loads(p.timeline.read_text(encoding="utf-8"))
            rows = timeline.get("shots", [])
            bad_frames = [r.get("shot_id") for r in rows
                          if (int(r.get("frames", 0)) - 1) % 4 != 0]
            check("时间轴 4n+1", not bad_frames,
                  "通过" if not bad_frames else "不合规：" + ",".join(map(str, bad_frames)))
        except Exception as exc:
            check("时间轴 JSON", False, str(exc))

    if p.shots.exists():
        try:
            pack = json.loads(p.shots.read_text(encoding="utf-8"))
            model = pack.get("model") or {}
            missing_keys = [k for k in ("unet", "clip", "vae", "width", "height", "steps") if k not in model]
            check("镜头包模型配置", not missing_keys,
                  "通过" if not missing_keys else "缺少：" + ",".join(missing_keys))
            missing = []
            for shot in pack.get("shots", []):
                image = p.resolve_asset(shot.get("img", ""))
                if not image.exists():
                    missing.append(f"{shot.get('id')}: {image}")
            check("首帧", not missing,
                  "全部存在" if not missing else "缺失 %d 个：%s" % (len(missing), "；".join(missing[:5])))
        except Exception as exc:
            check("镜头包 JSON", False, str(exc))

    if a.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("项目：%s / %s" % (p.root, p.episode))
        for item in result["checks"]:
            print("[%s] %s：%s" % ("通过" if item["ok"] else "失败", item["name"], item["detail"]))
        print("结论：%s" % ("可以进入生成" if result["ok"] else "先修复失败项，禁止直接出片"))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
