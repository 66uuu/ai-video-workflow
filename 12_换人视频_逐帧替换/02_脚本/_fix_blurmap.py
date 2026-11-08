import os, json, cv2, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "frames")
def imread_u(p):
    return cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_COLOR)
blur_map = {}
for i in range(1, 195):
    f = imread_u(os.path.join(SRC, "f%03d.png" % i))
    gray = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    blur_map[i] = round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 1)
with open(os.path.join(HERE, "_blur_map.json"), "w") as fp:
    json.dump(blur_map, fp)
vals = sorted(blur_map.values())
print("done. min=%.1f 中位=%.1f max=%.1f  方差<130帧数=%d" % (vals[0], vals[97], vals[-1], sum(1 for v in blur_map.values() if v < 130)))
