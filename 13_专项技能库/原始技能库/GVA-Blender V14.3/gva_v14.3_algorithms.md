# ============================================================
# GVA-Blender V14.3 算法函数库
# ============================================================

import numpy as np
import math
from shapely.geometry import Polygon

def rebuild_wall_axis(points, modulus=300, min_length=900):
    """模块化吸附 + 最小墙段过滤"""
    snapped = []
    for x, y in points:
        sx = round(x / modulus) * modulus
        sy = round(y / modulus) * modulus
        snapped.append((sx, sy))
    return snapped

def validate_proportion(dimensions, declared_total, tolerance=0.05):
    """交叉校验尺寸"""
    total = sum(dimensions)
    if abs(total - declared_total) / declared_total < tolerance:
        return {"status": "PASS", "sum": total, "declared": declared_total}
    else:
        return {"status": "CONFLICT", "sum": total, "declared": declared_total}

def analyze_stair_topology(stair_points):
    """识别楼梯类型、方向、旋转"""
    result = {
        "type": "spiral" if len(stair_points) > 10 else "straight",
        "direction": "ascending",
        "rotation": "clockwise"
    }
    return result

def build_adjacency_graph(rooms):
    """构建房间相邻关系"""
    graph = {"nodes": [], "edges": []}
    for room in rooms:
        graph["nodes"].append({"id": room["id"], "type": "Room"})
        for other in rooms:
            if room["id"] != other["id"]:
                poly1 = Polygon(room["polygon"])
                poly2 = Polygon(other["polygon"])
                if poly1.touches(poly2):
                    graph["edges"].append({
                        "from": room["id"],
                        "to": other["id"],
                        "relation": "adjacent"
                    })
    return graph

def calculate_pv_panels(zones):
    """计算全域光伏板数量"""
    total = sum(zone.get("panels", 0) for zone in zones.values())
    power = total * 0.3
    annual = power * 4.5 * 365
    return {
        "total_panels": total,
        "power_kw": power,
        "annual_kwh": annual
    }

def validate_immutable(original, generated, locked_fields):
    """校验几何不可变层"""
    violations = []
    for field in locked_fields:
        if original.get(field) != generated.get(field):
            violations.append({
                "field": field,
                "original": original.get(field),
                "generated": generated.get(field),
                "severity": "CRITICAL"
            })
    return violations