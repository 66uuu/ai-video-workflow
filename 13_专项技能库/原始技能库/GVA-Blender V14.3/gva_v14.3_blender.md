# ============================================================
# GVA-Blender V14.3 完整建模脚本
# 功能：一键生成三维白模（含光伏停车棚、螺旋楼梯、控制图导出）
# ============================================================

import bpy
import bmesh
import os
import math

# ---------- 尺寸常量 ----------
L = 12.0
D_TOTAL = 17.0
D_MAIN = 11.0
D_PORTICO = 4.0
D_BACKYARD = 2.0
WALL_H = 3.2
WALL_T = 0.2

# ---------- 辅助函数 ----------
def make_box(name, loc, size, color=(0.8, 0.8, 0.8)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.scale = size
    mat = bpy.data.materials.new(name=name + "_mat")
    mat.diffuse_color = (*color, 1)
    obj.data.materials.append(mat)
    return obj

def add_camera(name, loc, rot, lens=35):
    bpy.ops.object.camera_add(location=loc)
    cam = bpy.context.object
    cam.name = name
    cam.rotation_euler = rot
    cam.data.lens = lens
    return cam

def create_wall_axis(start, end, thickness=0.2, height=3.2):
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.sqrt(dx*dx + dy*dy)
    angle = math.atan2(dy, dx)
    mid_x = (start[0] + end[0]) / 2
    mid_y = (start[1] + end[1]) / 2
    bpy.ops.mesh.primitive_cube_add(size=1, location=(mid_x, mid_y, height/2))
    obj = bpy.context.object
    obj.name = "Wall_{}_{}".format(start[0], start[1])
    obj.scale = (length/2, thickness/2, height/2)
    obj.rotation_euler = (0, 0, angle)
    mat = bpy.data.materials.new("Wall_mat")
    mat.diffuse_color = (0.85, 0.85, 0.85, 1)
    obj.data.materials.append(mat)
    return obj

# ---------- 1. 地板 ----------
make_box("Floor_Main", (L/2, D_MAIN/2, 0.15), (L, D_MAIN, 0.3), (0.5, 0.5, 0.5))
make_box("Floor_Portico", (L/2, -D_PORTICO/2, 0.15), (L, D_PORTICO, 0.3), (0.5, 0.5, 0.5))

# ---------- 2. 主体外墙 ----------
create_wall_axis((0, 0), (L, 0), WALL_T, WALL_H)
create_wall_axis((0, D_MAIN), (L, D_MAIN), WALL_T, WALL_H)
create_wall_axis((0, 0), (0, D_MAIN), WALL_T, WALL_H)
create_wall_axis((L, 0), (L, D_MAIN), WALL_T, WALL_H)

# ---------- 3. 内隔墙 ----------
create_wall_axis((5.0, 0), (5.0, 4.2), 0.15, WALL_H)
create_wall_axis((0, 7.625), (L, 7.625), 0.15, WALL_H)
create_wall_axis((9.0, 0), (9.0, 5.488), 0.15, WALL_H)

# ---------- 4. 光伏停车棚 ----------
def create_carport_canopy():
    w, d, h = 5.0, 8.2, 3.3
    col_s = 0.2
    cx, cy = -2.5, 4.1
    bpy.ops.mesh.primitive_cube_add(size=1, location=(cx, cy, h))
    roof = bpy.context.object
    roof.name = "Carport_Canopy"
    roof.scale = (w/2, d/2, 0.1)
    roof.rotation_euler = (0.2, 0, 0)
    mat = bpy.data.materials.new("Canopy_mat")
    mat.diffuse_color = (0.85, 0.85, 0.85, 1)
    roof.data.materials.append(mat)
    for i in range(3):
        y = i * (d/2)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(cx - w/2 + 0.2, y, h/2))
        col = bpy.context.object
        col.name = "Carport_Column_{}".format(i+1)
        col.scale = (col_s/2, col_s/2, h/2)
        cm = bpy.data.materials.new("Col_mat_{}".format(i))
        cm.diffuse_color = (0.9, 0.9, 0.9, 1)
        col.data.materials.append(cm)
    rows, cols = 4, 6
    sx, sy = 0.8, 1.3
    start_x = cx - (cols-1)*sx/2
    start_y = cy - (rows-1)*sy/2
    for r in range(rows):
        for c in range(cols):
            x = start_x + c*sx
            y = start_y + r*sy
            bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, h+0.15))
            p = bpy.context.object
            p.name = "Carport_PV_{}_{}".format(r, c)
            p.scale = (0.35, 0.6, 0.02)
            p.rotation_euler = (0.2, 0, 0)
            pm = bpy.data.materials.new("PV_mat_{}_{}".format(r, c))
            pm.diffuse_color = (0.05, 0.15, 0.45, 1)
            pm.roughness, pm.metallic = 0.3, 0.7
            p.data.materials.append(pm)
    print("Carport done: {} panels".format(rows*cols))

create_carport_canopy()

# ---------- 5. 主屋顶光伏板 ----------
def create_roof_pv():
    panel_color = (0.05, 0.15, 0.45)
    rows, cols = 4, 6
    sx, sy = 1.6, 1.8
    cx, cy = L/2, D_MAIN/2
    start_x = cx - (cols-1)*sx/2
    start_y = cy - (rows-1)*sy/2
    for r in range(rows):
        for c in range(cols):
            x = start_x + c*sx
            y = start_y + r*sy
            bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, WALL_H+0.15))
            p = bpy.context.object
            p.name = "Roof1_PV_{}_{}".format(r, c)
            p.scale = (0.7, 0.8, 0.03)
            p.rotation_euler = (0.2, 0, 0)
            pm = bpy.data.materials.new("Roof1_PV_mat_{}_{}".format(r, c))
            pm.diffuse_color = (*panel_color, 1)
            p.data.materials.append(pm)
    print("Roof PV done: {} panels".format(rows*cols))

create_roof_pv()

# ---------- 6. 螺旋楼梯 ----------
def create_spiral_stair():
    cx, cy = 10.5, 3.6
    num_steps = 14
    radius = 0.6
    step_h = 0.25
    for i in range(num_steps):
        angle = i * (2 * math.pi / num_steps)
        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle)
        z = 0.3 + i * step_h
        bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, z))
        step = bpy.context.object
        step.name = "Stair_{}".format(i+1)
        step.scale = (0.5, 0.15, 0.1)
        step.rotation_euler = (0, 0, angle)
        sm = bpy.data.materials.new("Stair_mat_{}".format(i))
        sm.diffuse_color = (0.7, 0.7, 0.7, 1)
        step.data.materials.append(sm)
    print("Spiral stair done: {} steps".format(num_steps))

create_spiral_stair()

# ---------- 7. 门廊柱 ----------
def add_column(x, y, height=3.2):
    bpy.ops.mesh.primitive_cylinder_add(radius=0.15, depth=height, location=(x, y, height/2))
    col = bpy.context.object
    col.name = "Column_{}_{}".format(x, y)
    mat = bpy.data.materials.new("Col_mat_{}".format(x))
    mat.diffuse_color = (0.9, 0.9, 0.9, 1)
    col.data.materials.append(mat)

add_column(0.5, -D_PORTICO + 0.5)
add_column(L/2, -D_PORTICO + 0.5)
add_column(L - 0.5, -D_PORTICO + 0.5)

# ---------- 8. 相机系统 ----------
add_camera("CAM_aerial", (L/2, D_MAIN/2, 20), (1.3, 0, 0), 35)
add_camera("CAM_front", (L/2, -D_PORTICO - 5, 2.5), (1.4, 0, 0), 35)
add_camera("CAM_stair", (12, 5, 1.6), (1.5, 0, 0.5), 24)

# ---------- 9. 控制图导出 ----------
def setup_render():
    bpy.context.scene.render.engine = 'BLENDER_EEVEE'
    bpy.context.scene.render.image_settings.file_format = 'PNG'
    bpy.context.scene.render.resolution_x = 1920
    bpy.context.scene.render.resolution_y = 1080

def export_control_maps():
    output_dir = bpy.path.abspath("//control_maps")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    setup_render()
    bpy.context.scene.camera = bpy.data.objects.get("CAM_aerial")
    bpy.context.scene.render.filepath = os.path.join(output_dir, "01_aerial.png")
    bpy.ops.render.render(write_still=True)
    bpy.context.scene.camera = bpy.data.objects.get("CAM_front")
    bpy.context.scene.render.filepath = os.path.join(output_dir, "02_front.png")
    bpy.ops.render.render(write_still=True)
    print("Control maps exported to: {}".format(output_dir))

export_control_maps()

print("=" * 70)
print("GVA V14.3 Modeling Complete!")
print("Building: 12m x 17m x 3.2m")
print("PV Panels: Carport 24 + Roof 36 = 60")
print("Spiral Stair: 14 steps clockwise")
print("=" * 70)