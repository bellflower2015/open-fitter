import os
import sys

from algo_utils.bone_group_utils import (
    get_humanoid_and_auxiliary_bone_groups,
)
from algo_utils.mesh_topology_utils import check_edge_direction_similarity
from blender_utils.mesh_utils import get_evaluated_mesh
from math_utils.weight_utils import (
    calculate_weight_pattern_similarity,
)
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree
from scipy.spatial import cKDTree
import bmesh
import bpy
import math
import mathutils
import os
import sys
import time


# Merged from setup_weight_transfer.py

def setup_weight_transfer() -> None:
    """Setup the Robust Weight Transfer plugin settings."""
    try:
        bpy.context.scene.robust_weight_transfer_settings.source_object = bpy.data.objects["Body.BaseAvatar"]
    except Exception as e:
        raise Exception(f"Failed to setup weight transfer: {str(e)}")

# Merged from transfer_weights_from_nearest_vertex.py

def _validate_mesh(obj, label):
    if not obj or obj.type != 'MESH':
        return False
    return True


def _find_vertex_group(mesh, vertex_group_name):
    for vg in mesh.vertex_groups:
        if vg.name == vertex_group_name:
            return vg
    return None


def _ensure_object_mode():
    original_mode = bpy.context.mode
    if original_mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    return original_mode


def _restore_mode(original_mode):
    if original_mode != 'OBJECT' and original_mode.startswith('EDIT'):
        bpy.ops.object.mode_set(mode='EDIT')


def _ensure_target_vertex_group(target_obj, vertex_group_name):
    if vertex_group_name not in target_obj.vertex_groups:
        target_obj.vertex_groups.new(name=vertex_group_name)
    return target_obj.vertex_groups[vertex_group_name]


def _build_bvh_tree(body_bm):
    bvh_tree = BVHTree.FromBMesh(body_bm)
    return bvh_tree


def _compute_adjusted_normals(cloth_bm, bvh_tree, body_bm, body_normal_matrix, cloth_normal_matrix):
    adjusted_normals = {}

    for i, vertex in enumerate(cloth_bm.verts):
        cloth_vert_world = vertex.co
        original_normal_world = (cloth_normal_matrix @ Vector((vertex.normal[0], vertex.normal[1], vertex.normal[2], 0))).xyz.normalized()

        nearest_result = bvh_tree.find_nearest(cloth_vert_world)
        if nearest_result:
            _, _, nearest_face_index, _ = nearest_result
            face = body_bm.faces[nearest_face_index]
            face_normal_world = (body_normal_matrix @ Vector((face.normal[0], face.normal[1], face.normal[2], 0))).xyz.normalized()
            dot_product = original_normal_world.dot(face_normal_world)
            adjusted_normals[i] = -original_normal_world if dot_product < 0 else original_normal_world
        else:
            adjusted_normals[i] = original_normal_world

    return adjusted_normals


def _build_face_cache(cloth_bm, adjusted_normals):
    face_centers = []
    face_areas = {}
    face_adjusted_normals = {}
    face_indices = []

    for face in cloth_bm.faces:
        center = Vector((0, 0, 0))
        for v in face.verts:
            center += v.co
        center /= len(face.verts)
        face_centers.append(center)
        face_indices.append(face.index)

        face_areas[face.index] = face.calc_area()

        face_normal = Vector((0, 0, 0))
        for v in face.verts:
            face_normal += adjusted_normals[v.index]
        face_adjusted_normals[face.index] = face_normal.normalized()

    return face_centers, face_areas, face_adjusted_normals, face_indices


def _build_kdtree(face_centers):
    kd = cKDTree(face_centers)
    return kd


def _update_normals_with_weighted_average(cloth_bm, kd, face_centers, face_areas, face_adjusted_normals, face_indices, adjusted_normals, normal_radius):
    if normal_radius <= 0:
        return adjusted_normals

    for i, vertex in enumerate(cloth_bm.verts):
        co = vertex.co
        weighted_normal = Vector((0, 0, 0))
        total_weight = 0

        for index in kd.query_ball_point(co, normal_radius):
            face_index = face_indices[index]
            area = face_areas[face_index]
            dist = (co - face_centers[index]).length
            distance_factor = 1.0 - (dist / normal_radius) if dist < normal_radius else 0.0
            weight = area * distance_factor

            weighted_normal += face_adjusted_normals[face_index] * weight
            total_weight += weight

        if total_weight > 0:
            weighted_normal /= total_weight
            weighted_normal.normalize()
            adjusted_normals[i] = weighted_normal

    return adjusted_normals


def _get_vertex_group_weights(base_mesh_data, vg_index, v_indices):
    weights = []
    for v_idx in v_indices:
        w = 0.0
        try:
            for group in base_mesh_data.vertices[v_idx].groups:
                if group.group == vg_index:
                    w = group.weight
                    break
        except (IndexError, KeyError):
            pass
        weights.append(w)
    return weights


def _compute_barycentric_weight(face, base_vertex_group, base_mesh_data, closest_point_on_face):
    v0, v1, v2 = face.verts[0], face.verts[1], face.verts[2]
    vg_index = base_vertex_group.index
    w0, w1, w2 = _get_vertex_group_weights(base_mesh_data, vg_index, (v0.index, v1.index, v2.index))

    p0 = v0.co
    p1 = v1.co
    p2 = v2.co
    p = closest_point_on_face

    v0v1 = p1 - p0
    v0v2 = p2 - p0
    v0p = p - p0

    d00 = v0v1.dot(v0v1)
    d01 = v0v1.dot(v0v2)
    d11 = v0v2.dot(v0v2)
    d20 = v0p.dot(v0v1)
    d21 = v0p.dot(v0v2)

    denom = d00 * d11 - d01 * d01
    if abs(denom) > 1e-8:
        v = (d11 * d20 - d01 * d21) / denom
        w = (d00 * d21 - d01 * d20) / denom
        u = 1.0 - v - w
        weight = u * w0 + v * w1 + w * w2
        return max(0.0, min(1.0, weight))

    dist0 = (p - p0).length
    dist1 = (p - p1).length
    dist2 = (p - p2).length
    if dist0 <= dist1 and dist0 <= dist2:
        return w0
    if dist1 <= dist2:
        return w1
    return w2


def _apply_angle_weight(weight, cloth_normal_world, nearest_normal, angle_min_rad, angle_max_rad):
    if not nearest_normal:
        return weight

    angle = math.acos(min(1.0, max(-1.0, cloth_normal_world.dot(nearest_normal))))

    if angle > math.pi / 2:
        inverted_normal = -nearest_normal
        angle = math.acos(min(1.0, max(-1.0, cloth_normal_world.dot(inverted_normal))))

    if angle <= angle_min_rad:
        return 0.0
    if angle >= angle_max_rad:
        return weight

    angle_weight = (angle - angle_min_rad) / (angle_max_rad - angle_min_rad)
    return weight * angle_weight


def _compute_weight_for_vertex(vertex_index, vertex, cloth_normal_world, bvh_tree, body_bm, body_normal_matrix, base_vertex_group, base_mesh_data, angle_min_rad, angle_max_rad):
    cloth_vert_world = vertex.co
    nearest_result = bvh_tree.find_nearest(cloth_vert_world)
    weight = 0.0
    nearest_point = None
    nearest_normal = None

    if nearest_result:
        _, _, nearest_face_index, _ = nearest_result
        face = body_bm.faces[nearest_face_index]

        closest_point_on_face = mathutils.geometry.closest_point_on_tri(
            cloth_vert_world,
            face.verts[0].co,
            face.verts[1].co,
            face.verts[2].co
        )

        weight = _compute_barycentric_weight(face, base_vertex_group, base_mesh_data, closest_point_on_face)

        face_normal_world = (body_normal_matrix @ Vector((face.normal[0], face.normal[1], face.normal[2], 0))).xyz.normalized()
        nearest_point = closest_point_on_face
        nearest_normal = face_normal_world

    return _apply_angle_weight(weight, cloth_normal_world, nearest_normal, angle_min_rad, angle_max_rad)


def transfer_weights_from_nearest_vertex(base_mesh, target_obj, vertex_group_name, angle_min=-1.0, angle_max=-1.0, normal_radius=0.0):
    """
    base_meshの指定された頂点グループのウェイトをtarget_objに転写する
    
    target_objの各頂点において、最も近いbase_meshの頂点を取得し、そのウェイト値を設定する
    法線のなす角に基づいてウェイトを調整する
    
    Args:
        base_mesh: ベースメッシュオブジェクト（ウェイトのソース）
        target_obj: ターゲットメッシュオブジェクト（ウェイトの転写先）
        vertex_group_name (str): 転写する頂点グループ名
        angle_min (float): 角度の最小値、この値以下では ウェイト係数0.0（度単位）
        angle_max (float): 角度の最大値、この値以上では ウェイト係数1.0（度単位）
        normal_radius (float): 法線の加重平均を計算する際に考慮する球体の半径
    """
    
    if not _validate_mesh(base_mesh, 'ベースメッシュ') or not _validate_mesh(target_obj, 'ターゲットメッシュ'):
        return

    base_vertex_group = _find_vertex_group(base_mesh, vertex_group_name)
    if not base_vertex_group:
        return
    
    # モードを確認してオブジェクトモードに切り替え
    original_mode = _ensure_object_mode()
    
    angle_min_rad = math.radians(angle_min)
    angle_max_rad = math.radians(angle_max)
    
    body_bm = get_evaluated_mesh(base_mesh)
    body_bm.faces.ensure_lookup_table()

    bvh_tree = _build_bvh_tree(body_bm)

    target_vertex_group = _ensure_target_vertex_group(target_obj, vertex_group_name)

    cloth_bm = get_evaluated_mesh(target_obj)
    cloth_bm.verts.ensure_lookup_table()
    cloth_bm.faces.ensure_lookup_table()

    body_normal_matrix = base_mesh.matrix_world.inverted().transposed()
    cloth_normal_matrix = target_obj.matrix_world.inverted().transposed()

    adjusted_normals = _compute_adjusted_normals(cloth_bm, bvh_tree, body_bm, body_normal_matrix, cloth_normal_matrix)

    face_centers, face_areas, face_adjusted_normals, face_indices = _build_face_cache(cloth_bm, adjusted_normals)

    kd = _build_kdtree(face_centers)

    adjusted_normals = _update_normals_with_weighted_average(cloth_bm, kd, face_centers, face_areas, face_adjusted_normals, face_indices, adjusted_normals, normal_radius)
    
    base_mesh_data = base_mesh.data

    for i, vertex in enumerate(cloth_bm.verts):
        cloth_normal_world = adjusted_normals[i]
        weight = _compute_weight_for_vertex(
            i,
            vertex,
            cloth_normal_world,
            bvh_tree,
            body_bm,
            body_normal_matrix,
            base_vertex_group,
            base_mesh_data,
            angle_min_rad,
            angle_max_rad,
        )
        target_vertex_group.add([i], weight, 'REPLACE')

    _restore_mode(original_mode)

# Merged from create_overlapping_vertices_attributes.py

def create_overlapping_vertices_attributes(clothing_meshes, base_avatar_data, distance_threshold=0.0001, edge_angle_threshold=3, weight_similarity_threshold=0.1, overlap_attr_name="Overlapped", world_pos_attr_name="OriginalWorldPosition"):
    """
    ワールド座標上でほぼ重なっていて、ウェイトパターンが類似している頂点を検出し、
    カスタム頂点属性としてフラグ(1.0)を設定する。またワールド頂点座標も別の属性として保存する。
    
    Parameters:
        clothing_meshes: 処理対象の衣装メッシュのリスト
        base_avatar_data: ベースアバターデータ
        distance_threshold: 重なっていると判定する距離の閾値
        weight_similarity_threshold: ウェイトパターンの類似性閾値（小さいほど厳密）
        overlap_attr_name: 重なり頂点フラグ用のカスタム属性の名前
        world_pos_attr_name: ワールド座標を保存するカスタム属性の名前
    """
    print(f"Creating custom attributes for overlapping vertices with similar weight patterns...")
    
    # チェック対象の頂点グループを取得
    target_groups = get_humanoid_and_auxiliary_bone_groups(base_avatar_data)
    
    # 各メッシュに対して処理
    for mesh_obj in clothing_meshes:
        depsgraph = bpy.context.evaluated_depsgraph_get()
        eval_obj = mesh_obj.evaluated_get(depsgraph)
        mesh = eval_obj.data
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        
        # 頂点インデックスのマッピングを作成（BMesh内のインデックス → 元のメッシュのインデックス）
        vert_indices = {v.index: i for i, v in enumerate(bm.verts)}
        
        # 頂点データを収集
        all_vertices = []
        for vert_idx, vert in enumerate(bm.verts):
            # 頂点のワールド座標を計算
            world_pos = mesh_obj.matrix_world @ vert.co
            
            # 頂点に接続するエッジの方向ベクトルを収集
            edge_directions = []
            bm_vert = bm.verts[vert_idx]
            for edge in bm_vert.link_edges:
                other_vert = edge.other_vert(bm_vert)
                direction = (other_vert.co - bm_vert.co).normalized()
                edge_directions.append(direction)
            
            # 対象グループのウェイトを収集
            weights = {}
            orig_vert = mesh_obj.data.vertices[vert_indices[vert_idx]]
            for group_name in target_groups:
                if group_name in mesh_obj.vertex_groups:
                    group = mesh_obj.vertex_groups[group_name]
                    for g in orig_vert.groups:
                        if g.group == group.index:
                            weights[group_name] = g.weight
                            break
            
            # 頂点データを保存
            all_vertices.append({
                'vert_idx': vert_idx,
                'world_pos': world_pos,
                'edge_directions': edge_directions,
                'weights': weights
            })
        
        # KDTreeを構築して近接頂点を効率的に検索
        positions = [v['world_pos'] for v in all_vertices]
        kdtree = KDTree(len(positions))
        for i, pos in enumerate(positions):
            kdtree.insert(pos, i)
        kdtree.balance()
        
        # 重なり頂点用のカスタム属性を作成または取得
        if overlap_attr_name not in mesh_obj.data.attributes:
            mesh_obj.data.attributes.new(name=overlap_attr_name, type='FLOAT', domain='POINT')
        overlap_attr = mesh_obj.data.attributes[overlap_attr_name]
        
        # ワールド座標用のカスタム属性を作成または取得
        if world_pos_attr_name not in mesh_obj.data.attributes:
            mesh_obj.data.attributes.new(name=world_pos_attr_name, type='FLOAT_VECTOR', domain='POINT')
        pos_attr = mesh_obj.data.attributes[world_pos_attr_name]
        
        # 初期値を設定 (重なり属性は0、ワールド座標は現在の位置)
        for i, vertex in enumerate(mesh_obj.data.vertices):
            overlap_attr.data[i].value = 0.0
            world_position = mesh_obj.matrix_world @ vertex.co
            pos_attr.data[i].vector = world_position
        
        # 重なっている頂点を検出してフラグを設定
        processed = set()  # 処理済みの頂点インデックスを記録
        cluster_id = 0  # クラスタID（デバッグ用）
        
        for i, vert_data in enumerate(all_vertices):
            mesh_vertex_idx = vert_indices[all_vertices[i]['vert_idx']]
            world_pos = all_vertices[i]['world_pos']
            pos_attr.data[mesh_vertex_idx].vector = world_pos  # ワールド座標を保存

            if i in processed:
                continue
            
            # 近接頂点を検索
            overlapping_indices = []
            for (co, idx, dist) in kdtree.find_range(vert_data['world_pos'], distance_threshold):
                if idx != i and idx not in processed:  # 自分自身と処理済みの頂点は除外
                    # エッジ方向の類似性をチェック
                    if check_edge_direction_similarity(vert_data['edge_directions'], all_vertices[idx]['edge_directions'], edge_angle_threshold):
                        # ウェイトパターンの類似性をチェック
                        similarity = calculate_weight_pattern_similarity(
                            vert_data['weights'], all_vertices[idx]['weights'])
                        
                        # 類似性が閾値以上の場合のみ追加
                        if similarity >= (1.0 - weight_similarity_threshold):
                            overlapping_indices.append(idx)
            
            if not overlapping_indices:
                continue
            
            # 重なっている頂点グループを含める
            overlapping_indices.append(i)
            processed.add(i)
            
            
            # 重なっている頂点の属性を設定
            for vert_idx in overlapping_indices:
                mesh_vertex_idx = vert_indices[all_vertices[vert_idx]['vert_idx']]
                overlap_attr.data[mesh_vertex_idx].value = 1.0  # 重なり検出フラグを設定
                processed.add(vert_idx)
            
            cluster_id += 1
        
        # BMeshを解放
        bm.free()
        
        mesh_obj.data.update()
        
        print(f"Created custom attributes '{overlap_attr_name}' and '{world_pos_attr_name}' for {mesh_obj.name} with {cluster_id} overlapping vertex clusters")
