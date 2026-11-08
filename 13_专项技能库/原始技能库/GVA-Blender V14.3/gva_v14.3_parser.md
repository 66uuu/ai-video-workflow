# ============================================================
# GVA-Blender V14.3 DXF Parser
# 功能：从DXF提取主体建筑数据，生成控制图
# ============================================================

import ezdxf
import matplotlib.pyplot as plt
import json
import os

MAIN_LAYERS = [
    "WALL", "COLUMN", "BEAM", "SLAB",
    "WINDOW", "DOOR_FIRE", "BALCONY",
    "STAIR", "ROOF", "WALL-PARAPET",
    "CURTWALL", "SPACE_HOUSE"
]

def extract_wall_axes(dxf_path):
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    walls = []
    for e in msp:
        if e.dxf.layer not in MAIN_LAYERS:
            continue
        if e.dxftype() == "LINE" and e.dxf.layer == "WALL":
            walls.append({
                "start": [round(e.dxf.start.x, 2), round(e.dxf.start.y, 2)],
                "end": [round(e.dxf.end.x, 2), round(e.dxf.end.y, 2)]
            })
    return walls

def extract_openings(dxf_path):
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    openings = []
    for e in msp.query("INSERT"):
        layer = e.dxf.layer.upper()
        is_door = "DOOR" in layer
        is_window = "WINDOW" in layer
        if is_door or is_window:
            openings.append({
                "type": "door" if is_door else "window",
                "position": [round(e.dxf.insert.x, 2), round(e.dxf.insert.y, 2)],
                "block": e.dxf.name
            })
    return openings

def render_control_map(dxf_path, output_png):
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    fig, ax = plt.subplots(figsize=(20, 16))
    ax.set_aspect('equal')
    ax.set_facecolor('black')
    count = 0
    for e in msp:
        if e.dxf.layer not in MAIN_LAYERS:
            continue
        if e.dxftype() == "LINE":
            ax.plot([e.dxf.start.x, e.dxf.end.x],
                    [e.dxf.start.y, e.dxf.end.y], 'w-', linewidth=2)
            count += 1
        elif e.dxftype() == "LWPOLYLINE":
            pts = list(e.get_points(format="xy"))
            for i in range(len(pts)-1):
                ax.plot([pts[i][0], pts[i+1][0]],
                        [pts[i][1], pts[i+1][1]], 'w-', linewidth=2)
            count += 1
        elif e.dxftype() == "INSERT":
            ax.plot(e.dxf.insert.x, e.dxf.insert.y, 'wo', markersize=8)
            count += 1
    ax.axis('off')
    plt.savefig(output_png, dpi=300, bbox_inches='tight', facecolor='black')
    plt.close()
    print("Generated: {} ({} objects)".format(output_png, count))

if __name__ == "__main__":
    files = [
        ("floor_1.dxf", "01_floor1.png"),
        ("floor_2.dxf", "02_floor2.png"),
        ("floor_3.dxf", "03_floor3.png"),
    ]
    for dxf_file, png_file in files:
        if os.path.exists(dxf_file):
            render_control_map(dxf_file, png_file)
        else:
            print("Not found: {}".format(dxf_file))
    print("All done!")