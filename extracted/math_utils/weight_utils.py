import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from algo_utils.bone_group_utils import (
    get_humanoid_and_auxiliary_bone_groups,
)
from blender_utils.mesh_utils import get_evaluated_mesh
from blender_utils.subdivision_utils import subdivide_selected_vertices
from dataclasses import dataclass
from mathutils import Vector
from mathutils.bvhtree import BVHTree
import bpy
import numpy as np
import os
import sys

# Merged from calculate_weight_pattern_similarity.py

def calculate_weight_pattern_similarity(weights1, weights2):
    """
    2つのウェイトパターン間の類似性を計算する
    
    Parameters:
        weights1: 1つ目のウェイトパターン {group_name: weight}
        weights2: 2つ目のウェイトパターン {group_name: weight}
        
    Returns:
        float: 類似度（0.0〜1.0、1.0が完全一致）
    """
    # 両方のパターンに存在するグループを取得
    all_groups = set(weights1.keys()) | set(weights2.keys())
    
    if not all_groups:
        return 0.0
    
    # 各グループのウェイト差の合計を計算
    total_diff = 0.0
    for group in all_groups:
        w1 = weights1.get(group, 0.0)
        w2 = weights2.get(group, 0.0)
        total_diff += abs(w1 - w2)
    
    # 正規化（グループ数で割る）
    normalized_diff = total_diff / len(all_groups)
    
    # 類似度に変換（差が小さいほど類似度が高い）
    similarity = 1.0 - min(normalized_diff, 1.0)
    
    return similarity

# Merged from normalize_vertex_weights.py

def normalize_vertex_weights(obj):
    """
    指定されたメッシュオブジェクトのボーンウェイトを正規化する。
    Args:
        obj: 正規化するメッシュオブジェクト
    """
    if obj.type != 'MESH':
        print(f"Error: {obj.name} is not a mesh object")
        return

    # 頂点グループが存在するか確認
    if not obj.vertex_groups:
        print(f"Warning: {obj.name} has no vertex groups")
        return
        
    # 各頂点が少なくとも1つのグループに属しているか確認
    for vert in obj.data.vertices:
        if not vert.groups:
            print(f"Warning: Vertex {vert.index} in {obj.name} has no weights")
    
    # Armatureモディファイアの確認
    has_armature = any(mod.type == 'ARMATURE' for mod in obj.modifiers)
    if not has_armature:
        print(f"Error: {obj.name} has no Armature modifier")
        return
    
    # すべての選択を解除
    bpy.ops.object.select_all(action='DESELECT')

    # アクティブオブジェクトを設定
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='OBJECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    
    # ウェイトの正規化を実行
    bpy.ops.object.vertex_group_normalize_all(
        group_select_mode='BONE_DEFORM',
        lock_active=False
    )
    print(f"Normalized weights for {obj.name}")

# Merged from normalize_bone_weights.py

def normalize_bone_weights(obj: bpy.types.Object, avatar_data: dict) -> None:
    """
    メッシュのボーン変形に関わる頂点ウェイトを正規化する。
    
    Parameters:
        obj: メッシュオブジェクト
        avatar_data: アバターデータ
    """
    if obj.type != 'MESH':
        return
        
    # 正規化対象のボーングループを取得
    target_groups = set()
    # Humanoidボーンを追加
    for bone_map in avatar_data.get("humanoidBones", []):
        if "boneName" in bone_map:
            target_groups.add(bone_map["boneName"])
    
    # 補助ボーンを追加
    for aux_set in avatar_data.get("auxiliaryBones", []):
        for aux_bone in aux_set.get("auxiliaryBones", []):
            target_groups.add(aux_bone)
    
    # 各頂点について処理
    for vert in obj.data.vertices:
        # ターゲットグループのウェイト合計を計算
        total_weight = 0.0
        weights = {}
        
        for g in vert.groups:
            group_name = obj.vertex_groups[g.group].name
            if group_name in target_groups:
                total_weight += g.weight
                weights[group_name] = g.weight
        
        # ウェイトの正規化
        for group_name, weight in weights.items():
            normalized_weight = weight / total_weight
            obj.vertex_groups[group_name].add([vert.index], normalized_weight, 'REPLACE')

# Merged from calculate_distance_based_weights.py

def calculate_distance_based_weights(source_obj_name, target_obj_name, vertex_group_name="DistanceWeight", min_distance=0.0, max_distance=0.03):
    """
    指定されたオブジェクトの各頂点から別のオブジェクトまでの最近接面距離を計測し、
    距離に基づいて頂点ウェイトを設定する関数
    
    Args:
        source_obj_name (str): ウェイトを設定するオブジェクト名
        target_obj_name (str): 距離計測対象のオブジェクト名
        vertex_group_name (str): 作成する頂点グループ名
        min_distance (float): 最小距離（ウェイト1.0になる距離）
        max_distance (float): 最大距離（ウェイト0.0になる距離）
    """
    
    # オブジェクトを取得
    source_obj = bpy.data.objects.get(source_obj_name)
    target_obj = bpy.data.objects.get(target_obj_name)
    
    if not source_obj:
        print(f"エラー: オブジェクト '{source_obj_name}' が見つかりません")
        return False
    
    if not target_obj:
        print(f"エラー: オブジェクト '{target_obj_name}' が見つかりません")
        return False
    
    # メッシュデータを取得
    source_mesh = source_obj.data
    target_mesh = target_obj.data
    
    # 頂点グループを作成または取得
    if vertex_group_name not in source_obj.vertex_groups:
        vertex_group = source_obj.vertex_groups.new(name=vertex_group_name)
    else:
        vertex_group = source_obj.vertex_groups[vertex_group_name]
    
    # ターゲットオブジェクトのBVHTreeを作成
    print("BVHTreeを構築中...")
    
    # ターゲットメッシュのワールド座標での頂点とポリゴンを取得
    target_verts = []
    target_polys = []
    
    # 評価されたメッシュを取得（モディファイアが適用された状態）
    depsgraph = bpy.context.evaluated_depsgraph_get()
    target_eval = target_obj.evaluated_get(depsgraph)
    target_mesh_eval = target_eval.data
    
    # ワールド座標に変換
    target_matrix = target_obj.matrix_world
    
    for vert in target_mesh_eval.vertices:
        world_co = target_matrix @ vert.co
        target_verts.append(world_co)
    
    for poly in target_mesh_eval.polygons:
        target_polys.append(poly.vertices)
    
    # BVHTreeを構築
    bvh = BVHTree.FromPolygons(target_verts, target_polys)
    
    # ソースオブジェクトの各頂点について処理
    source_matrix = source_obj.matrix_world
    source_eval = source_obj.evaluated_get(depsgraph)
    source_mesh_eval = source_eval.data
    
    weights = []
    
    for i, vert in enumerate(source_mesh_eval.vertices):
        # 頂点のワールド座標を取得
        world_co = source_matrix @ vert.co
        
        # 最近接面までの距離を計算
        location, normal, index, distance = bvh.find_nearest(world_co)
        
        if location is None:
            distance = max_distance
        
        # 距離に基づいてウェイトを計算
        if distance <= min_distance:
            weight = 1.0
        elif distance >= max_distance:
            weight = 0.0
        else:
            # 線形補間でウェイトを計算（max_distanceに近づくほど0に近づく）
            weight = 1.0 - ((distance - min_distance) / (max_distance - min_distance))
        
        weights.append(weight)
        
        # 頂点グループにウェイトを設定
        vertex_group.add([i], weight, 'REPLACE')
    
    return True

# Merged from normalize_overlapping_vertices_weights.py

@dataclass
class OverlapContext:
    target_groups: list
    distance_threshold: float = 0.0001


class _OverlapNormalizationContext:
    """Orchestrates overlapping-vertex weight normalization per mesh."""

    def __init__(self, clothing_meshes, base_avatar_data, overlap_attr_name, world_pos_attr_name):
        self.clothing_meshes = clothing_meshes
        self.overlap_attr_name = overlap_attr_name
        self.world_pos_attr_name = world_pos_attr_name
        self.original_active = bpy.context.view_layer.objects.active
        self.ctx = OverlapContext(
            target_groups=get_humanoid_and_auxiliary_bone_groups(base_avatar_data),
            distance_threshold=0.0001,
        )
        self.valid_meshes = []

    def filter_valid_meshes(self):
        self.valid_meshes = _filter_valid_meshes(
            self.clothing_meshes, self.overlap_attr_name, self.world_pos_attr_name
        )
        return self.valid_meshes

    def _process_mesh(self, mesh_obj):
        overlap_attr = mesh_obj.data.attributes[self.overlap_attr_name]
        world_pos_attr = mesh_obj.data.attributes[self.world_pos_attr_name]

        work_obj = _duplicate_work_object(mesh_obj)
        overlapping_verts_ids = _find_overlapping_vertex_indices(overlap_attr)

        if not overlapping_verts_ids:
            bpy.data.objects.remove(work_obj, do_unlink=True)
            return

        subdivide_selected_vertices(work_obj.name, overlapping_verts_ids, level=2)
        subdiv_overlap_attr = work_obj.data.attributes[self.overlap_attr_name]
        subdiv_overlapping_verts_ids = _find_overlapping_vertex_indices(subdiv_overlap_attr)
        subdiv_world_pos_attr = work_obj.data.attributes[self.world_pos_attr_name]

        subdiv_original_world_positions = _collect_world_positions(
            subdiv_world_pos_attr, subdiv_overlapping_verts_ids
        )
        overlapping_groups = _group_vertices_by_position(
            subdiv_overlapping_verts_ids,
            subdiv_original_world_positions,
            self.ctx.distance_threshold,
        )
        _, vert_weights = _compute_reference_weights(
            work_obj,
            mesh_obj,
            self.ctx.target_groups,
            overlapping_groups,
        )

        bpy.ops.object.select_all(action='DESELECT')
        mesh_obj.select_set(True)
        bpy.context.view_layer.objects.active = mesh_obj

        updated_count = _apply_weights_to_original(
            mesh_obj,
            world_pos_attr,
            overlapping_verts_ids,
            subdiv_overlapping_verts_ids,
            subdiv_original_world_positions,
            vert_weights,
            self.ctx.distance_threshold,
        )

        bpy.data.objects.remove(work_obj, do_unlink=True)
    def process_all(self):
        if not self.valid_meshes:
            print(
                f"警告: {self.overlap_attr_name}と{self.world_pos_attr_name}属性を持つメッシュが見つかりません。処理をスキップします。"
            )
            return

        for mesh_obj in self.valid_meshes:
            self._process_mesh(mesh_obj)

    def restore_active(self):
        bpy.context.view_layer.objects.active = self.original_active


def _filter_valid_meshes(clothing_meshes, overlap_attr_name, world_pos_attr_name):
    return [
        mesh
        for mesh in clothing_meshes
        if (
            overlap_attr_name in mesh.data.attributes
            and world_pos_attr_name in mesh.data.attributes
            and "InpaintMask" in mesh.vertex_groups
        )
    ]


def _duplicate_work_object(mesh_obj):
    bpy.ops.object.select_all(action='DESELECT')
    mesh_obj.select_set(True)
    bpy.context.view_layer.objects.active = mesh_obj
    bpy.ops.object.duplicate(linked=False)
    work_obj = bpy.context.active_object
    work_obj.name = f"{mesh_obj.name}_OverlapWork"
    return work_obj


def _find_overlapping_vertex_indices(overlap_attr, threshold=0.9999):
    return [i for i, data in enumerate(overlap_attr.data) if data.value > threshold]


def _collect_world_positions(world_pos_attr, vertex_indices):
    return [Vector(world_pos_attr.data[vert_idx].vector) for vert_idx in vertex_indices]


def _group_vertices_by_position(vertex_indices, positions, distance_threshold):
    overlapping_groups = {}
    for orig_idx, world_pos in zip(vertex_indices, positions):
        for group_id, (group_pos, members) in overlapping_groups.items():
            if (world_pos - group_pos).length <= distance_threshold:
                members.append(orig_idx)
                break
        else:
            group_id = len(overlapping_groups)
            overlapping_groups[group_id] = (world_pos, [orig_idx])
    return overlapping_groups


def _compute_reference_weights(work_obj, mesh_obj, target_groups, overlapping_groups):
    reference_weights = {}
    vert_weights = {}

    for group_id, (group_pos, member_indices) in overlapping_groups.items():
        member_inpaint_weights = []
        for idx in member_indices:
            inpaint_weight = 0.0
            if "InpaintMask" in work_obj.vertex_groups:
                inpaint_group = work_obj.vertex_groups["InpaintMask"]
                for g in work_obj.data.vertices[idx].groups:
                    if g.group == inpaint_group.index:
                        inpaint_weight = g.weight
                        break
            member_inpaint_weights.append((idx, inpaint_weight))

        member_inpaint_weights.sort(key=lambda x: x[1])

        if not member_inpaint_weights:
            continue

        reference_idx = member_inpaint_weights[0][0]
        ref_weights = {}
        for group_name in target_groups:
            if group_name in work_obj.vertex_groups:
                group = work_obj.vertex_groups[group_name]
                weight = 0.0
                for g in work_obj.data.vertices[reference_idx].groups:
                    if g.group == group.index:
                        weight = g.weight
                        break
                ref_weights[group_name] = weight

        reference_weights[group_id] = ref_weights

        min_inpaint_weight = member_inpaint_weights[0][1]
        same_weight_vert_ids = [v[0] for v in member_inpaint_weights if abs(v[1] - min_inpaint_weight) < 0.0001]
        same_weight_verts = [work_obj.data.vertices[idx] for idx in same_weight_vert_ids]

        if len(same_weight_verts) > 1:
            avg_weights = {}
            for group_name in target_groups:
                if group_name in work_obj.vertex_groups:
                    weights_sum = 0.0
                    count = 0
                    for v in same_weight_verts:
                        weight = 0.0
                        for g in v.groups:
                            if g.group == mesh_obj.vertex_groups[group_name].index:
                                weight = g.weight
                                break
                        if weight > 0:
                            weights_sum += weight
                            count += 1
                    if count > 0:
                        avg_weights[group_name] = weights_sum / count
            reference_weights[group_id] = avg_weights

        for vert_idx in member_indices:
            vert_weights[vert_idx] = reference_weights[group_id].copy()

    return reference_weights, vert_weights


def _apply_weights_to_original(
    mesh_obj,
    world_pos_attr,
    overlapping_verts_ids,
    subdiv_overlapping_verts_ids,
    subdiv_original_world_positions,
    vert_weights,
    distance_threshold,
):
    updated_count = 0
    for orig_idx in overlapping_verts_ids:
        orig_world_pos = Vector(world_pos_attr.data[orig_idx].vector)
        closest_idx = None
        min_dist = float("inf")

        for subdiv_idx, subdiv_pos in zip(subdiv_overlapping_verts_ids, subdiv_original_world_positions):
            dist = (orig_world_pos - subdiv_pos).length
            if dist < min_dist:
                min_dist = dist
                closest_idx = subdiv_idx

        if closest_idx is not None and closest_idx in vert_weights and min_dist < distance_threshold:
            for group_name, weight in vert_weights[closest_idx].items():
                if group_name in mesh_obj.vertex_groups:
                    mesh_obj.vertex_groups[group_name].add([orig_idx], weight, "REPLACE")
            updated_count += 1

    return updated_count


def normalize_overlapping_vertices_weights(clothing_meshes, base_avatar_data, overlap_attr_name="Overlapped", world_pos_attr_name="OriginalWorldPosition"):
    """
    Overlapped属性が1となる頂点で構成される面およびエッジのみを対象に
    重なっている頂点のウェイトを正規化する
    
    Parameters:
        clothing_meshes: 処理対象の衣装メッシュのリスト
        base_avatar_data: ベースアバターデータ
        overlap_attr_name: 重なり検出フラグの属性名
        world_pos_attr_name: ワールド座標が保存された属性名
    """
    print("Normalizing weights for overlapping vertices using custom attributes...")

    ctx = _OverlapNormalizationContext(
        clothing_meshes,
        base_avatar_data,
        overlap_attr_name,
        world_pos_attr_name,
    )

    try:
        ctx.filter_valid_meshes()
        ctx.process_all()
    finally:
        ctx.restore_active()
# Merged from create_distance_falloff_transfer_mask.py

def create_distance_falloff_transfer_mask(obj: bpy.types.Object, 
                                        base_avatar_data: dict,
                                        group_name: str = "DistanceFalloffMask",
                                        max_distance: float = 0.025,
                                        min_distance: float = 0.002) -> bpy.types.VertexGroup:
    """
    距離に基づいて減衰するTransferMask頂点グループを作成
    
    Parameters:
        obj: 対象のメッシュオブジェクト
        base_avatar_data: ベースアバターのデータ
        group_name: 生成する頂点グループの名前（デフォルト: "DistanceFalloffMask"）
        max_distance: ウェイトが0になる最大距離（デフォルト: 0.025）
        min_distance: ウェイトが1になる最小距離（デフォルト: 0.002）
        
    Returns:
        bpy.types.VertexGroup: 生成された頂点グループ
    """
    # 入力チェック
    if obj.type != 'MESH':
        print(f"Error: {obj.name} is not a mesh object")
        return None

    # ソースオブジェクト(Body.BaseAvatar)の取得
    source_obj = bpy.data.objects.get("Body.BaseAvatar")
    if not source_obj:
        print("Error: Body.BaseAvatar not found")
        return None

    # モディファイア適用後のターゲットメッシュを取得
    target_bm = get_evaluated_mesh(source_obj)
    target_bm.faces.ensure_lookup_table()

    # ターゲットメッシュのBVHツリーを作成
    bvh = BVHTree.FromBMesh(target_bm)

    # モディファイア適用後のソースメッシュを取得
    source_bm = get_evaluated_mesh(obj)
    source_bm.verts.ensure_lookup_table()

    # 新しい頂点グループを作成
    transfer_mask = obj.vertex_groups.new(name=group_name)

    # 各頂点を処理
    for vert_idx, vert in enumerate(obj.data.vertices):

        # モディファイア適用後の頂点位置を使用
        evaluated_vertex_co = source_bm.verts[vert_idx].co

        # 最近接点と法線を取得
        location, normal, index, distance = bvh.find_nearest(evaluated_vertex_co)

        if location is not None:
            # 距離に基づいてベースウェイトを計算
            if distance > max_distance:
                weight = 0.0
            else:
                d = distance - min_distance
                if d < 0.0:
                    d = 0.0
                weight = 1.0 - d / (max_distance - min_distance)

        # 頂点グループに追加
        transfer_mask.add([vert_idx], weight, 'REPLACE')

    # BMeshをクリーンアップ
    source_bm.free()
    target_bm.free()

    return transfer_mask

# Merged from get_vertex_weight_safe.py

def get_vertex_weight_safe(target_obj, group, vertex_index):
    """
    頂点グループからウェイトを安全に取得する。
    
    Args:
        target_obj: 対象のBlenderオブジェクト
        group: 頂点グループ
        vertex_index: 頂点インデックス
        
    Returns:
        float: ウェイト値（グループがない場合や取得に失敗した場合は0.0）
    """
    if not group:
        return 0.0
    try:
        for g in target_obj.data.vertices[vertex_index].groups:
            if g.group == group.index:
                return g.weight
    except Exception:
        return 0.0
    return 0.0

# Merged from generate_weight_hash.py

def generate_weight_hash(weights):
    """ウェイト辞書からハッシュ値を生成する（0.001より小さい部分を四捨五入）"""
    sorted_items = sorted(weights.items())
    # ウェイト値を0.001の精度で四捨五入
    hash_str = "_".join([f"{name}:{round(weight, 3):.3f}" for name, weight in sorted_items])
    return hash_str