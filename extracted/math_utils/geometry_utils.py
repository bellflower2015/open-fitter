import os
import sys

from mathutils import Vector
import bpy
import numpy as np
import os
import sys


# Merged from calculate_vertices_world.py

def calculate_vertices_world(mesh_obj):
    """
    変形後のメッシュの頂点のワールド座標を取得
    
    Args:
        mesh_obj: メッシュオブジェクト
    Returns:
        vertices_world: ワールド座標のnumpy配列
    """
    # 変形後のメッシュを取得
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated_obj = mesh_obj.evaluated_get(depsgraph)
    evaluated_mesh = evaluated_obj.data
    
    # ワールド座標に変換（変形後の頂点位置を使用）
    vertices_world = np.array([evaluated_obj.matrix_world @ v.co for v in evaluated_mesh.vertices])
    
    return vertices_world

# Merged from calculate_component_size.py

def calculate_component_size(coords):
    """
    コンポーネントのサイズを計算する
    
    Parameters:
        coords: 頂点座標のリスト
        
    Returns:
        float: コンポーネントのサイズ（直径または最大の辺の長さ）
    """
    if len(coords) < 2:
        return 0.0
    
    # バウンディングボックスを計算
    min_x = min(co.x for co in coords)
    max_x = max(co.x for co in coords)
    min_y = min(co.y for co in coords)
    max_y = max(co.y for co in coords)
    min_z = min(co.z for co in coords)
    max_z = max(co.z for co in coords)
    
    # バウンディングボックスの対角線の長さを計算
    diagonal = ((max_x - min_x)**2 + (max_y - min_y)**2 + (max_z - min_z)**2)**0.5
    
    return diagonal

# Merged from barycentric_coords_from_point.py

def barycentric_coords_from_point(p, a, b, c):
    """
    三角形上の点pの重心座標を計算する
    
    Args:
        p: 点の座標（Vector）
        a, b, c: 三角形の頂点座標（Vector）
    
    Returns:
        (u, v, w): 重心座標のタプル（u + v + w = 1）
    """
    v0 = b - a
    v1 = c - a
    v2 = p - a
    
    d00 = v0.dot(v0)
    d01 = v0.dot(v1)
    d11 = v1.dot(v1)
    d20 = v2.dot(v0)
    d21 = v2.dot(v1)
    
    denom = d00 * d11 - d01 * d01
    
    if abs(denom) < 1e-10:
        # 退化した三角形の場合は最も近い頂点のウェイトを1にする
        dist_a = (p - a).length
        dist_b = (p - b).length
        dist_c = (p - c).length
        min_dist = min(dist_a, dist_b, dist_c)
        if min_dist == dist_a:
            return (1.0, 0.0, 0.0)
        elif min_dist == dist_b:
            return (0.0, 1.0, 0.0)
        else:
            return (0.0, 0.0, 1.0)
    
    v = (d11 * d20 - d01 * d21) / denom
    w = (d00 * d21 - d01 * d20) / denom
    u = 1.0 - v - w
    
    return (u, v, w)

# Merged from check_mesh_obb_intersection.py

def check_mesh_obb_intersection(mesh_obj, obb):
    """
    メッシュとOBBの交差をチェックする
    
    Parameters:
        mesh_obj: チェック対象のメッシュオブジェクト
        obb: OBB情報（中心、軸、半径）
        
    Returns:
        bool: 交差する場合はTrue
    """
    if obb is None:
        return False
    
    # 評価済みメッシュを取得
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = mesh_obj.evaluated_get(depsgraph)
    eval_mesh = eval_obj.data
    
    # メッシュの頂点をOBB空間に変換して交差チェック
    for v in eval_mesh.vertices:
        # 頂点のワールド座標
        vertex_world = mesh_obj.matrix_world @ v.co
        
        # OBBの中心からの相対位置
        relative_pos = vertex_world - Vector(obb['center'])
        
        # OBBの各軸に沿った投影
        projections = [abs(relative_pos.dot(Vector(obb['axes'][:, i]))) for i in range(3)]
        
        # すべての軸で投影が半径以内なら交差
        if all(proj <= radius for proj, radius in zip(projections, obb['radii'])):
            return True
    
    return False