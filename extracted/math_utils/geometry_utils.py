import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from algo_utils.vertex_group_utils import get_vertex_groups_and_weights
from mathutils import Matrix
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

# Merged from transform_utils.py

# Merged from list_to_matrix.py

def list_to_matrix(matrix_list):
    """
    リストからMatrix型に変換する（JSON読み込み用）
    
    Parameters:
        matrix_list: list - 行列のデータを含む2次元リスト
        
    Returns:
        Matrix: 変換された行列
    """
    return Matrix(matrix_list)

# Merged from apply_similarity_transform_to_points.py

def apply_similarity_transform_to_points(points, s, R, t):
    """
    点群に相似変換を適用する
    
    Parameters:
        points: 変換する点群 (Nx3 のNumPy配列)
        s: スケーリング係数 (スカラー)
        R: 回転行列 (3x3)
        t: 平行移動ベクトル (3x1)
        
    Returns:
        transformed_points: 変換後の点群 (Nx3 のNumPy配列)
    """
    return s * (R @ points.T).T + t

# Merged from calculate_optimal_similarity_transform.py

def calculate_optimal_similarity_transform(source_points, target_points):
    """
    2つの点群間の最適な相似変換（スケール、回転、平行移動）を計算する
    
    Parameters:
        source_points: 変換元の点群 (Nx3 のNumPy配列)
        target_points: 変換先の点群 (Nx3 のNumPy配列)
        
    Returns:
        (s, R, t): スケーリング係数 (スカラー), 回転行列 (3x3), 平行移動ベクトル (3x1)
    """
    # 点群の重心を計算
    centroid_source = np.mean(source_points, axis=0)
    centroid_target = np.mean(target_points, axis=0)
    
    # 重心を原点に移動
    source_centered = source_points - centroid_source
    target_centered = target_points - centroid_target
    
    # ソース点群の二乗和を計算（スケーリング係数の計算用）
    source_scale = np.sum(source_centered**2)
    
    # 共分散行列を計算
    H = source_centered.T @ target_centered
    
    # 特異値分解
    U, S, Vt = np.linalg.svd(H)
    
    # 回転行列を計算
    R = Vt.T @ U.T
    
    # 反射を防ぐ（行列式が負の場合）
    if np.linalg.det(R) < 0:
        Vt[-1, :] *= -1
        R = Vt.T @ U.T
    
    # 最適なスケーリング係数を計算
    trace_RSH = np.sum(S)
    s = trace_RSH / source_scale if source_scale > 0 else 1.0
    
    # 平行移動ベクトルを計算
    t = centroid_target - s * (R @ centroid_source)
    
    return s, R, t

# Merged from calculate_inverse_pose_matrix.py

def calculate_inverse_pose_matrix(mesh_obj, armature_obj, vertex_index):
    """指定された頂点のポーズ逆行列を計算"""

    # 頂点グループとウェイトの取得
    weights = get_vertex_groups_and_weights(mesh_obj, vertex_index)
    if not weights:
        return None

    # 最終的な変換行列の初期化
    final_matrix = Matrix.Identity(4)
    final_matrix.zero()
    total_weight = 0

    # 各ボーンの影響を計算
    for bone_name, weight in weights.items():
        if weight > 0 and bone_name in armature_obj.data.bones:
            bone = armature_obj.data.bones[bone_name]
            pose_bone = armature_obj.pose.bones.get(bone_name)
            if bone and pose_bone:
                # ボーンの最終的な行列を計算
                mat = armature_obj.matrix_world @ \
                      pose_bone.matrix @ \
                      bone.matrix_local.inverted() @ \
                      armature_obj.matrix_world.inverted()
                
                # ウェイトを考慮して行列を加算
                final_matrix += mat * weight
                total_weight += weight

    # ウェイトの合計で正規化
    if total_weight > 0:
        final_matrix = final_matrix * (1.0 / total_weight)

    # 逆行列を計算して返す
    try:
        return final_matrix.inverted()
    except Exception as e:
        return Matrix.Identity(4)

# Merged from copy_bone_transform.py

def copy_bone_transform(source_bone: bpy.types.EditBone, target_bone: bpy.types.EditBone) -> None:
    """
    Copy transformation data from source bone to target bone.
    
    Parameters:
        source_bone: Source edit bone
        target_bone: Target edit bone
    """
    target_bone.head = source_bone.head.copy()
    target_bone.tail = source_bone.tail.copy()
    target_bone.roll = source_bone.roll
    target_bone.matrix = source_bone.matrix.copy()
    target_bone.length = source_bone.length

# Merged from obb_utils.py

try:
    import bpy
except ImportError:
    bpy = None


def calculate_obb(vertices_world):
    """
    頂点のワールド座標から最適な向きのバウンディングボックスを計算
    
    Parameters:
        vertices_world: 頂点のワールド座標のリスト
        
    Returns:
        (axes, extents): 主軸方向と、各方向の半分の長さ
    """
    if vertices_world is None or len(vertices_world) < 3:
        return None, None
    
    # 点群の重心を計算
    centroid = np.mean(vertices_world, axis=0)
    
    # 重心を原点に移動
    centered = vertices_world - centroid
    
    # 共分散行列を計算
    cov = np.cov(centered, rowvar=False)
    
    # 固有ベクトルと固有値を計算
    eigenvalues, eigenvectors = np.linalg.eigh(cov)
    
    # 固有ベクトルが主軸となる
    axes = eigenvectors
    
    # 各軸方向のextentを計算
    extents = np.zeros(3)
    for i in range(3):
        axis = axes[:, i]
        projection = np.dot(centered, axis)
        extents[i] = (np.max(projection) - np.min(projection)) / 2.0
    
    return axes, extents


def calculate_obb_from_object(obj):
    """
    オブジェクトのOriented Bounding Box (OBB)を計算する
    
    Parameters:
        obj: 対象のメッシュオブジェクト
        
    Returns:
        dict: OBBの情報（中心、軸、半径）
    """
    if bpy is None:
        raise ImportError("bpy module required for calculate_obb_from_object")
    
    # 評価済みメッシュを取得
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    eval_mesh = eval_obj.data
    
    # 頂点座標をワールド空間で取得
    vertices = np.array([obj.matrix_world @ v.co for v in eval_mesh.vertices])
    
    if len(vertices) == 0:
        return None
    
    # 頂点の平均位置（中心）を計算
    center = np.mean(vertices, axis=0)
    
    # 中心を原点に移動
    centered_vertices = vertices - center
    
    # 共分散行列を計算
    covariance_matrix = np.cov(centered_vertices.T)
    
    # 固有値と固有ベクトルを計算
    eigenvalues, eigenvectors = np.linalg.eigh(covariance_matrix)
    
    # 固有ベクトルを正規化
    for i in range(3):
        eigenvectors[:, i] = eigenvectors[:, i] / np.linalg.norm(eigenvectors[:, i])
    
    # 各軸に沿った投影の最大値を計算
    min_proj = np.full(3, float('inf'))
    max_proj = np.full(3, float('-inf'))
    
    for vertex in centered_vertices:
        for i in range(3):
            proj = np.dot(vertex, eigenvectors[:, i])
            min_proj[i] = min(min_proj[i], proj)
            max_proj[i] = max(max_proj[i], proj)
    
    # 半径（各軸方向の長さの半分）を計算
    radii = (max_proj - min_proj) / 2
    
    # 中心位置を調整
    adjusted_center = center + np.sum([(min_proj[i] + max_proj[i]) / 2 * eigenvectors[:, i] for i in range(3)], axis=0)
    
    return {
        'center': adjusted_center,
        'axes': eigenvectors,
        'radii': radii
    }


def calculate_obb_from_points(points):
    """
    点群からOriented Bounding Box (OBB)を計算する
    
    Parameters:
        points: 点群のリスト（Vector型またはタプル）
        
    Returns:
        dict: OBBの情報を含む辞書
            'center': 中心座標
            'axes': 主軸（3x3の行列、各列が軸）
            'radii': 各軸方向の半径
        または None: 計算不能な場合
    """
    
    # 点群が少なすぎる場合はNoneを返す
    if len(points) < 3:
        print(f"警告: 点群が少なすぎます（{len(points)}点）。OBB計算をスキップします。")
        return None
    
    try:
        # 点群をnumpy配列に変換
        points_np = np.array([[p.x, p.y, p.z] for p in points])
        
        # 点群の中心を計算
        center = np.mean(points_np, axis=0)
        
        # 中心を原点に移動
        centered_points = points_np - center
        
        # 共分散行列を計算
        cov_matrix = np.cov(centered_points, rowvar=False)
        
        # 行列のランクをチェック
        if np.linalg.matrix_rank(cov_matrix) < 3:
            print("警告: 共分散行列のランクが不足しています。OBB計算をスキップします。")
            return None
        
        # 固有値と固有ベクトルを計算
        eigenvalues, eigenvectors = np.linalg.eigh(cov_matrix)
        
        # 固有値が非常に小さい場合はスキップ
        if np.any(np.abs(eigenvalues) < 1e-10):
            print("警告: 固有値が非常に小さいです。OBB計算をスキップします。")
            return None
        
        # 固有値の大きさでソート（降順）
        idx = eigenvalues.argsort()[::-1]
        eigenvalues = eigenvalues[idx]
        eigenvectors = eigenvectors[:, idx]
        
        # 主軸を取得（列ベクトルとして）
        axes = eigenvectors
        
        # 各軸方向の点の投影を計算
        projections = np.abs(np.dot(centered_points, axes))
        
        # 各軸方向の最大値を半径として使用
        radii = np.max(projections, axis=0)
        
        # 結果を辞書として返す
        return {
            'center': center,
            'axes': axes,
            'radii': radii
        }
    except Exception as e:
        return None