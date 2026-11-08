#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
render.py — ComfyUI 通用工作流渲染器（仅标准库）
读一个 API-format 工作流 JSON，按节点 id 覆盖字段，POST 到本机 ComfyUI，
轮询 /history，下载成品。

用法示例（FLUX）:
  python render.py --workflow flux_schnell_gguf.json --out out.png \
      --text 5:"a man ..." --size 7:1024x1024 --seed 8:42 --prefix 11:flux

用法示例（SD1.5）:
  python render.py --workflow sd15_t2i.json --out sd.png \
      --text 4:"a man ..." --neg 5:"blurry, worst quality" \
      --size 3:512x768 --seed 6:42 --prefix 9:sd15 --steps 6:28

--text  ID:文本    覆盖 id 号节点的 inputs.text（正向提示词）
--neg   ID:文本    覆盖为负向提示词（同一个 --text 目标）
--size  ID:WxH     覆盖该节点 inputs.width/height（若存在）
--seed  ID:N       覆盖该节点 inputs.seed
--steps ID:N       覆盖该节点 inputs.steps
--prefix ID:str    覆盖该节点 inputs.filename_prefix
"""
import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

BASE = os.environ.get("COMFY_URL", "http://127.0.0.1:8188")


def _post(path, data):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def _get(path):
    with urllib.request.urlopen(BASE + path, timeout=60) as r:
        return r.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workflow", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--text", action="append", default=[])
    ap.add_argument("--neg", action="append", default=[])
    ap.add_argument("--size", action="append", default=[])
    ap.add_argument("--seed", action="append", default=[])
    ap.add_argument("--steps", action="append", default=[])
    ap.add_argument("--prefix", action="append", default=[])
    args = ap.parse_args()

    with open(args.workflow, "r", encoding="utf-8") as f:
        g = json.load(f)

    def node(nid):
        return g[str(nid)]["inputs"]

    def split_spec(s, sep):
        # "ID:value"  or "ID=value"
        a, _, b = s.partition(sep)
        return a, b

    for s in args.text:              # --text 5:prompt
        nid, val = split_spec(s, ":")
        node(nid)["text"] = val
    for s in args.neg:               # --neg 5:negative
        nid, val = split_spec(s, ":")
        node(nid)["text"] = val
    for s in args.size:              # --size 7:1024x1024
        nid, val = split_spec(s, ":")
        w, _, h = val.partition("x")
        if "width" in node(nid):
            node(nid)["width"] = int(w)
        if "height" in node(nid):
            node(nid)["height"] = int(h)
    for s in args.seed:              # --seed 8:42
        nid, val = split_spec(s, ":")
        node(nid)["seed"] = int(val)
    for s in args.steps:             # --steps 8:4
        nid, val = split_spec(s, ":")
        if "steps" in node(nid):
            node(nid)["steps"] = int(val)
    for s in args.prefix:            # --prefix 11:flux
        nid, val = split_spec(s, ":")
        node(nid)["filename_prefix"] = val

    client_id = str(uuid.uuid4())
    t0 = time.time()
    try:
        resp = _post("/prompt", {"prompt": g, "client_id": client_id})
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        print(f"[提交失败] HTTP {e.code}:\n{body}")
        return 2
    except Exception as e:
        print(f"[提交失败] {e}")
        return 2
    print(f"[已入队] {resp['prompt_id']}  ({os.path.basename(args.workflow)})")

    deadline = time.time() + 2400
    out_image = None
    while time.time() < deadline:
        try:
            hist = json.loads(_get(f"/history/{resp['prompt_id']}").decode("utf-8"))
        except Exception:
            time.sleep(2); continue
        entry = hist.get(resp["prompt_id"])
        if entry:
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                msgs = status.get("messages", [])
                print(f"[ComfyUI 执行出错] {msgs}")
                return 3
            if entry.get("outputs"):
                for no in entry["outputs"].values():
                    for img in no.get("images", []):
                        out_image = img
        if out_image:
            break
        time.sleep(3)

    if not out_image:
        print("[失败] 超时或未拿到输出（可能 OOM，检查 ComfyUI 前台/日志）")
        return 4

    # download
    url = (f"{BASE}/view?filename={urllib.parse.quote(out_image['filename'], safe='')}"
           f"&subfolder={urllib.parse.quote(out_image.get('subfolder', ''), safe='')}"
           f"&type={out_image.get('type', 'output')}")
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with urllib.request.urlopen(url, timeout=300) as r, open(args.out, "wb") as fo:
        fo.write(r.read())
    print(f"[完成] {os.path.abspath(args.out)}  用时 {time.time()-t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
