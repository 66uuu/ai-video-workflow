#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
身份一致性质检（ArcFace 余弦）
==============================
解决：drift_check.py 只能测「画面有没有变形」，测不出「脸还是不是同一个人」。
本脚本直接跑本机已有的人脸权重，给每张图 / 每段视频一个身份相似度分数。

用到的权重（ComfyUI 自带，无需下载）：
  <D盘>\\ComfyUI\\models\\insightface\\models\\buffalo_l\\det_10g.onnx    SCRFD 人脸检测
  <D盘>\\ComfyUI\\models\\insightface\\models\\buffalo_l\\w600k_r50.onnx  ArcFace 特征

依赖只有 numpy / cv2 / onnxruntime，全在 ComfyUI venv 里。

用法：
  python qa_identity.py --ref "锚点脸.png" --target "关键帧目录"
  python qa_identity.py --ref "锚点脸.png" --target "S09.mp4" --frames 8
  python qa_identity.py --ref "锚点脸.png" --target "镜头目录" --csv out.csv

判读（ArcFace 余弦，越大越像）：
  >= 0.55   PASS       同一人
  0.40-0.55 CONCERNS   可能是同一人，建议人工看一眼
  < 0.40    FAIL       不是同一人 / 检不到脸
"""
import argparse
import csv
import glob
import os
import sys

import cv2
import numpy as np
import onnxruntime as ort

DEFAULT_MODELS = r"ComfyUI\models\insightface\models\buffalo_l"

# ArcFace 标准 5 点模板（112x112）
ARCFACE_TEMPLATE = np.array([
    [38.2946, 51.6963],
    [73.5318, 51.5014],
    [56.0252, 71.7366],
    [41.5493, 92.3655],
    [70.7299, 92.2041],
], dtype=np.float32)

STRIDES = (8, 16, 32)
NUM_ANCHORS = 2
INPUT_SIZE = 640
SCORE_THRESH = 0.5
NMS_THRESH = 0.4


# ── 人脸检测（SCRFD） ──────────────────────────────────────────

class SCRFD:
    def __init__(self, model_path):
        self.sess = ort.SessionOptions()
        self.sess.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.net = ort.InferenceSession(model_path, self.sess, providers=["CPUExecutionProvider"])
        self.input_name = self.net.get_inputs()[0].name
        self.outputs = self.net.get_outputs()

        # ONNX 里输出维度常是动态(None)，只能先空跑一次拿真实 shape
        dummy = np.zeros((1, 3, INPUT_SIZE, INPUT_SIZE), dtype=np.float32)
        probe = self.net.run(None, {self.input_name: dummy})

        # 按输出 shape 分组：最后一维 1=分数 / 4=框 / 10=关键点
        groups = {}
        for o, arr in zip(self.outputs, probe):
            shape = arr.shape
            if len(shape) < 2:
                continue
            # det_10g 的输出是 (N, C)：N=锚点数，C=1/4/10
            n = int(shape[0])
            last = int(shape[-1])
            groups.setdefault(n, {})[last] = o.name
        self.pairs = []
        for n, d in groups.items():
            if set(d) >= {1, 4, 10}:
                # 反推 stride：640/stride 的平方 * 2 anchors == n
                stride = None
                for s in STRIDES:
                    if (INPUT_SIZE // s) ** 2 * NUM_ANCHORS == n:
                        stride = s
                        break
                if stride:
                    self.pairs.append((stride, d[1], d[4], d[10]))
        if not self.pairs:
            raise SystemExit("SCRFD 输出结构与预期不符，无法解析")

    def detect(self, img):
        h0, w0 = img.shape[:2]
        scale = INPUT_SIZE / max(h0, w0)
        resized = cv2.resize(img, (int(w0 * scale), int(h0 * scale)))
        canvas = np.zeros((INPUT_SIZE, INPUT_SIZE, 3), dtype=np.uint8)
        canvas[:resized.shape[0], :resized.shape[1]] = resized
        blob = cv2.dnn.blobFromImage(canvas, 1 / 128.0, (INPUT_SIZE, INPUT_SIZE),
                                     (127.5, 127.5, 127.5), swapRB=True)
        outs = self.net.run(None, {self.input_name: blob})
        name2out = {o.name: outs[i] for i, o in enumerate(self.outputs)}

        boxes, scores, kpss = [], [], []
        for stride, s_name, b_name, k_name in self.pairs:
            sc = name2out[s_name].reshape(-1)
            bb = name2out[b_name].reshape(-1, 4) * stride
            kp = name2out[k_name].reshape(-1, 10) * stride
            fh = INPUT_SIZE // stride
            idx = np.where(sc >= SCORE_THRESH)[0]
            if idx.size == 0:
                continue
            for i in idx:
                anchor = i
                row = anchor // (fh * NUM_ANCHORS)
                col = (anchor // NUM_ANCHORS) % fh
                cx = col * stride
                cy = row * stride
                d = bb[i]
                boxes.append([cx - d[0], cy - d[1], cx + d[2], cy + d[3]])
                scores.append(float(sc[i]))
                k = kp[i]
                kpss.append([[cx + k[2 * j], cy + k[2 * j + 1]] for j in range(5)])

        if not boxes:
            return []
        boxes = np.array(boxes, dtype=np.float32) / scale
        scores = np.array(scores, dtype=np.float32)
        keep = self._nms(boxes, scores)
        return [(boxes[i], scores[i], np.array(kpss[i], dtype=np.float32) / scale) for i in keep]

    @staticmethod
    def _nms(boxes, scores):
        x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
        areas = (x2 - x1) * (y2 - y1)
        order = scores.argsort()[::-1]
        keep = []
        while order.size:
            i = order[0]
            keep.append(i)
            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])
            inter = np.maximum(0.0, xx2 - xx1) * np.maximum(0.0, yy2 - yy1)
            iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-6)
            order = order[1:][iou <= NMS_THRESH]
        return keep


# ── ArcFace 特征 ──────────────────────────────────────────────

class ArcFace:
    def __init__(self, model_path):
        self.net = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        self.input_name = self.net.get_inputs()[0].name

    def embed(self, face_bgr, kps):
        M = cv2.estimateAffinePartial2D(kps, ARCFACE_TEMPLATE, method=cv2.LMEDS)[0]
        if M is None:
            return None
        aligned = cv2.warpAffine(face_bgr, M, (112, 112), borderValue=0.0)
        blob = cv2.dnn.blobFromImage(aligned, 1.0 / 127.5, (112, 112), (127.5, 127.5, 127.5), swapRB=True)
        v = self.net.run(None, {self.input_name: blob})[0].reshape(-1)
        n = np.linalg.norm(v)
        return v / n if n > 0 else None


def cosine(a, b):
    return float(np.dot(a, b))


# ── 取图 ──────────────────────────────────────────────────────

def read_images(path, frames_per_video=8):
    """图片返回一张；视频均匀抽帧。返回 [(标签, BGR)]"""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
        img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
        return [("frame", img)] if img is not None else []
    if ext in (".mp4", ".mov", ".avi", ".mkv"):
        cap = cv2.VideoCapture(path)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        out = []
        if total > 0:
            picks = np.linspace(0, max(total - 1, 0), min(frames_per_video, total)).astype(int)
            for k in picks:
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(k))
                ok, img = cap.read()
                if ok and img is not None:
                    out.append(("%06d" % k, img))
        cap.release()
        return out
    return []


def first_face_vec(path, det, arc):
    """取一张图里最大那张脸的特征向量；检不到返回 None"""
    for _tag, img in read_images(path):
        faces = det.detect(img)
        if not faces:
            return None
        faces.sort(key=lambda f: (f[0][2] - f[0][0]) * (f[0][3] - f[0][1]), reverse=True)
        return arc.embed(img, faces[0][2])
    return None


def face_vecs(img, det, arc, min_w=0.04):
    """
    返回画面里所有够大的脸：[(特征向量, 脸宽占画宽比例)]
    同框镜头里林砚不一定是最大那张，所以逐脸都算，最后取最像本主的那张。
    min_w=0.04 用来滤掉海报、手机屏这类小脸。
    """
    faces = det.detect(img)
    if not faces:
        return []
    out = []
    for box, _score, kps in faces:
        w_ratio = (box[2] - box[0]) / float(img.shape[1])
        if w_ratio < min_w:
            continue
        vec = arc.embed(img, kps)
        if vec is not None:
            out.append((vec, w_ratio))
    return out


def verdict_of(cos_ref, margin, has_neg, th_pass, th_fail, m_pass, m_fail):
    """
    有负样本时按「相对判据」裁定：跟本人锚点的相似度，要比跟任何别的角色锚点都高出足够多。
    这样阈值不受打光/角度/画幅影响，只问「是不是这个人」。没有负样本时退回绝对阈值。
    """
    if has_neg:
        if margin >= m_pass:
            return "PASS"
        if margin >= m_fail:
            return "CONCERNS"
        return "FAIL"
    if cos_ref >= th_pass:
        return "PASS"
    if cos_ref >= th_fail:
        return "CONCERNS"
    return "FAIL"


def collect_targets(target):
    if "," in target and not os.path.exists(target):
        # 支持 --target "a.mp4,b.mp4,c.mp4" 只测指定几镜
        out = []
        for part in target.split(","):
            part = part.strip()
            if part:
                out += collect_targets(part)
        return out
    if os.path.isdir(target):
        files = []
        for pat in ("*.png", "*.jpg", "*.jpeg", "*.mp4", "*.mov"):
            files += glob.glob(os.path.join(target, pat))
        return sorted(files)
    return [target]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True, help="参考脸图（锚点/定妆照）")
    ap.add_argument("--target", required=True, help="图片 / 视频 / 目录")
    ap.add_argument("--models", default=DEFAULT_MODELS)
    ap.add_argument("--frames", type=int, default=8, help="每个视频抽帧数")
    ap.add_argument("--csv", default="", help="结果写到 CSV")
    ap.add_argument("--pass", dest="th_pass", type=float, default=0.55)
    ap.add_argument("--fail", dest="th_fail", type=float, default=0.40)
    ap.add_argument("--neg", default="",
                    help="其他角色锚点：逗号分隔的图片，或一个目录。给了就按相对判据裁定")
    ap.add_argument("--margin-pass", dest="m_pass", type=float, default=0.20)
    ap.add_argument("--margin-fail", dest="m_fail", type=float, default=0.08)
    a = ap.parse_args()

    det_p = os.path.join(a.models, "det_10g.onnx")
    arc_p = os.path.join(a.models, "w600k_r50.onnx")
    for p in (det_p, arc_p):
        if not os.path.exists(p):
            raise SystemExit("找不到人脸权重：%s" % p)

    det = SCRFD(det_p)
    arc = ArcFace(arc_p)

    ref_vec = first_face_vec(a.ref, det, arc)
    if ref_vec is None:
        raise SystemExit("参考图里没检到脸：%s" % a.ref)

    # 负样本：别的角色锚点。给了就按「相对判据」裁定，不受打光/角度影响
    neg_vecs = []
    if a.neg:
        neg_files = []
        for part in a.neg.split(","):
            part = part.strip()
            if not part:
                continue
            neg_files += collect_targets(part)
        ref_stem = os.path.splitext(os.path.basename(a.ref))[0]
        for f in neg_files:
            if os.path.splitext(os.path.basename(f))[0] == ref_stem:
                continue
            v = first_face_vec(f, det, arc)
            if v is not None:
                neg_vecs.append((os.path.basename(f), v))
        if not neg_vecs:
            raise SystemExit("--neg 里一张脸都没检到，检查路径")
        print("负样本 %d 张：%s" % (len(neg_vecs), "、".join(n for n, _ in neg_vecs)))

    targets = collect_targets(a.target)
    if not targets:
        raise SystemExit("目标里没有可读文件：%s" % a.target)

    has_neg = bool(neg_vecs)
    rows = []
    for t in targets:
        imgs = read_images(t, a.frames)
        if not imgs:
            rows.append({"target": os.path.basename(t), "frames": 0, "rate": 0.0,
                         "cos": "", "top5": "", "neg": "", "margin": "",
                         "verdict": "FAIL", "note": "读不了文件"})
            continue
        picks = []
        for _tag, img in imgs:
            cand = []
            for vec, w_ratio in face_vecs(img, det, arc):
                cos_ref = cosine(ref_vec, vec)
                if has_neg:
                    hit = max(neg_vecs, key=lambda nv: cosine(nv[1], vec))
                    cos_neg = cosine(hit[1], vec)
                else:
                    cos_neg = None
                cand.append({"cos": cos_ref, "neg": cos_neg,
                             "margin": (cos_ref - cos_neg) if cos_neg is not None else None,
                             "w": w_ratio})
            if not cand:
                continue
            # 一帧里可能有多张脸，取最像本主的那张
            picks.append(max(cand, key=lambda p: p["cos"]))
        if not picks:
            rows.append({"target": os.path.basename(t), "frames": len(imgs), "rate": 0.0,
                         "cos": "", "top5": "", "neg": "", "margin": "",
                         "verdict": "FAIL", "note": "整段没检到脸"})
            continue
        picks.sort(key=lambda p: p["cos"], reverse=True)
        best = picks[0]
        top5 = float(np.mean([p["cos"] for p in picks[:5]]))
        rate = len(picks) / float(len(imgs))
        margin = best["margin"] if has_neg else 0.0
        verdict = verdict_of(best["cos"], margin, has_neg,
                             a.th_pass, a.th_fail, a.m_pass, a.m_fail)
        notes = []
        if rate < 0.5:
            notes.append("检出率低(%.0f%%)" % (rate * 100))
        if best["w"] < 0.06:
            notes.append("人脸太小")
        rows.append({"target": os.path.basename(t), "frames": len(imgs), "rate": rate,
                     "cos": best["cos"], "top5": top5,
                     "neg": "" if best["neg"] is None else best["neg"],
                     "margin": "" if not has_neg else margin,
                     "verdict": verdict, "note": "；".join(notes)})

    head = "%-24s %4s %6s %7s %7s" % ("target", "抽帧", "检出率", "本人cos", "前5均")
    if has_neg:
        head += " %7s %7s" % ("最像别人", "差值")
    print(head + "  " + "裁定")
    for r in rows:
        if r["cos"] == "":
            print("%-24s  %s" % (r["target"][:24], r["note"]))
            continue
        line = "%-24s %4d %5.0f%% %7.3f %7.3f" % (
            r["target"][:24], r["frames"], r["rate"] * 100, r["cos"], r["top5"])
        if has_neg:
            line += " %7.3f %7.3f" % (r["neg"], r["margin"])
        print(line + "  " + r["verdict"] + ("  " + r["note"] if r["note"] else ""))

    if a.csv:
        with open(a.csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["target", "frames", "detect_rate", "cos_ref", "top5_mean",
                        "cos_neg_max", "margin", "verdict", "note"])
            for r in rows:
                w.writerow([r["target"], r["frames"], r["rate"], r["cos"], r["top5"],
                            r["neg"], r["margin"], r["verdict"], r["note"]])
        print("CSV：%s" % a.csv)


if __name__ == "__main__":
    main()
