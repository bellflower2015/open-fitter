import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from algo_utils.bone_group_utils import (
    get_humanoid_and_auxiliary_bone_groups,
)
from algo_utils.vertex_group_utils import check_uniform_weights
from dataclasses import dataclass
from math_utils.geometry_utils import calculate_component_size
from math_utils.geometry_utils import calculate_obb
from math_utils.geometry_utils import calculate_obb_from_points
from math_utils.geometry_utils import check_mesh_obb_intersection
from math_utils.weight_utils import generate_weight_hash
from mathutils import Vector
from typing import Dict, List, Optional, Set, Tuple
import bmesh
import bpy
import numpy as np
import os
import sys

# Merged from find_connected_components.py

def find_connected_components(mesh_obj):
    """
    メッシュオブジェクト内で接続していないコンポーネントを検出する
    
    Parameters:
        mesh_obj: 検出対象のメッシュオブジェクト
        
    Returns:
        List[Set[int]]: 各コンポーネントに含まれる頂点インデックスのセットのリスト
    """
    # BMeshを作成し、元のメッシュからデータをコピー
    bm = bmesh.new()
    bm.from_mesh(mesh_obj.data)
    bm.verts.ensure_lookup_table()
    
    # 頂点インデックスのマッピングを作成（BMesh内のインデックス → 元のメッシュのインデックス）
    vert_indices = {v.index: i for i, v in enumerate(bm.verts)}
    
    # 未訪問の頂点を追跡
    unvisited = set(vert_indices.keys())
    components = []
    
    while unvisited:
        # 未訪問の頂点から開始
        start_idx = next(iter(unvisited))
        
        # 幅優先探索で連結成分を検出
        component = set()
        queue = [start_idx]
        
        while queue:
            current = queue.pop(0)
            if current in unvisited:
                unvisited.remove(current)
                component.add(vert_indices[current])  # 元のメッシュのインデックスに変換して追加
                
                # 隣接頂点をキューに追加（エッジで接続されている頂点のみ）
                for edge in bm.verts[current].link_edges:
                    other = edge.other_vert(bm.verts[current]).index
                    if other in unvisited:
                        queue.append(other)
        
        # 頂点数が1のコンポーネント（孤立頂点）は除外
        if len(component) > 1:
            components.append(component)
    
    bm.free()
    return components

# Merged from group_components_by_weight_pattern.py

@dataclass
class _WeightPatternContext:
    obj: bpy.types.Object
    base_obj: bpy.types.Object
    bm: bmesh.types.BMesh
    target_groups: set
    existing_target_groups: set
    rigid_group: bpy.types.VertexGroup
    tolerance: float = 0.0001
    round_digits: int = 4
    rigid_group_name: str = "Rigid2"


def _build_context(obj, base_avatar_data, clothing_armature, bm):
    base_obj = bpy.data.objects.get("Body.BaseAvatar")
    if not base_obj:
        raise Exception("Base avatar mesh (Body.BaseAvatar) not found")

    target_groups = get_humanoid_and_auxiliary_bone_groups(base_avatar_data)
    if clothing_armature:
        target_groups.update(bone.name for bone in clothing_armature.data.bones)

    existing_target_groups = {vg.name for vg in obj.vertex_groups if vg.name in target_groups}

    rigid_group_name = "Rigid2"
    if rigid_group_name not in obj.vertex_groups:
        obj.vertex_groups.new(name=rigid_group_name)
    rigid_group = obj.vertex_groups[rigid_group_name]

    return _WeightPatternContext(
        obj=obj,
        base_obj=base_obj,
        bm=bm,
        target_groups=target_groups,
        existing_target_groups=existing_target_groups,
        rigid_group=rigid_group,
    )


def _collect_component_weights(ctx: _WeightPatternContext, component):
    vertex_weights = []
    for vert_idx in component:
        vert = ctx.obj.data.vertices[vert_idx]
        weights = {group: 0.0 for group in ctx.existing_target_groups}
        for g in vert.groups:
            group_name = ctx.obj.vertex_groups[g.group].name
            if group_name in ctx.existing_target_groups:
                weights[group_name] = g.weight
        vertex_weights.append(weights)
    return vertex_weights


def _is_uniform_pattern(vertex_weights, existing_target_groups, tolerance):
    if not vertex_weights:
        return False, None
    first_weights = vertex_weights[0]
    for weights in vertex_weights[1:]:
        for group_name in existing_target_groups:
            if abs(weights[group_name] - first_weights[group_name]) >= tolerance:
                return False, None
    return True, first_weights


def _component_world_points(ctx: _WeightPatternContext, component):
    points = []
    for idx in component:
        if idx < len(ctx.bm.verts):
            points.append(ctx.obj.matrix_world @ ctx.bm.verts[idx].co)
    return points


def _should_exclude_by_intersection(ctx: _WeightPatternContext, component_points):
    if len(component_points) < 3:
        return False
    obb = calculate_obb_from_points(component_points)
    if obb is None:
        return False
    if check_mesh_obb_intersection(ctx.base_obj, obb):
        print(
            f"Component with {len(component_points)} vertices intersects with base mesh, excluding from rigid transfer"
        )
        return True
    return False


def _pattern_key(first_weights, round_digits):
    return tuple(sorted((k, round(v, round_digits)) for k, v in first_weights.items() if v > 0))


def _apply_rigid(ctx: _WeightPatternContext, component):
    for vert_idx in component:
        ctx.rigid_group.add([vert_idx], 1.0, "REPLACE")


def _debug_dump_patterns(obj_name, components, component_patterns):
    print(f"Found {len(components)} connected components in {obj_name}")
    print(f"Found {len(component_patterns)} uniform weight patterns in {obj_name}")
    for i, (pattern, components_list) in enumerate(component_patterns.items()):
        total_vertices = sum(len(comp) for comp in components_list)
        for j, comp in enumerate(components_list):
            print(f"    Component {j}: {len(comp)} vertices")


def group_components_by_weight_pattern(obj, base_avatar_data, clothing_armature):
    """
    同じウェイトパターンを持つ連結成分をグループ化する
    
    Parameters:
        obj: 処理対象のメッシュオブジェクト
        base_avatar_data: ベースアバターデータ
        
    Returns:
        dict: ウェイトパターンをキー、連結成分のリストを値とする辞書
    """
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        ctx = _build_context(obj, base_avatar_data, clothing_armature, bm)

        components = find_connected_components(obj)
        component_patterns = {}
        uniform_components = []

        for component in components:
            vertex_weights = _collect_component_weights(ctx, component)
            if not vertex_weights:
                continue

            is_uniform, first_weights = _is_uniform_pattern(
                vertex_weights, ctx.existing_target_groups, ctx.tolerance
            )
            if not is_uniform:
                continue

            component_points = _component_world_points(ctx, component)
            if _should_exclude_by_intersection(ctx, component_points):
                continue

            uniform_components.append(component)

            pattern_tuple = _pattern_key(first_weights, ctx.round_digits)
            if pattern_tuple:
                _apply_rigid(ctx, component)
                if pattern_tuple not in component_patterns:
                    component_patterns[pattern_tuple] = []
                component_patterns[pattern_tuple].append(component)

        _debug_dump_patterns(obj.name, components, component_patterns)
        return component_patterns
    finally:
        bm.free()


def process_weight_patterns(obj, base_avatar_data, clothing_armature):
    """Thin wrapper to align with other process_* entrypoints."""
    return group_components_by_weight_pattern(obj, base_avatar_data, clothing_armature)

# Merged from cluster_components_by_adaptive_distance.py

def cluster_components_by_adaptive_distance(component_coords, component_sizes):
    """
    コンポーネント間の距離に基づいてクラスタリングする（サイズに応じた適応的な閾値を使用）
    
    Parameters:
        component_coords: コンポーネントインデックスをキー、頂点座標のリストを値とする辞書
        component_sizes: コンポーネントインデックスをキー、サイズを値とする辞書
        
    Returns:
        list: クラスターのリスト（各クラスターはコンポーネントインデックスのリスト）
    """
    if not component_coords:
        return []
    
    # 各コンポーネントの中心点を計算
    centers = {}
    for comp_idx, coords in component_coords.items():
        if coords:
            center = Vector((0, 0, 0))
            for co in coords:
                center += co
            center /= len(coords)
            centers[comp_idx] = center
    
    # クラスターのリスト（初期状態では各コンポーネントが独立したクラスター）
    clusters = [[comp_idx] for comp_idx in centers.keys()]
    
    # コンポーネントの平均サイズを計算
    if component_sizes:
        average_size = sum(component_sizes.values()) / len(component_sizes)
    else:
        average_size = 0.1  # デフォルト値
    
    # 最小閾値と最大閾値を設定
    min_threshold = 0.1
    max_threshold = 1.0
    
    # クラスターをマージする
    merged = True
    while merged:
        merged = False
        
        # 各クラスターペアをチェック
        for i in range(len(clusters)):
            if i >= len(clusters):  # クラスター数が変わった場合の安全チェック
                break
                
            for j in range(i + 1, len(clusters)):
                if j >= len(clusters):  # クラスター数が変わった場合の安全チェック
                    break
                    
                # 各クラスター内のコンポーネント間の最小距離と関連するサイズを計算
                min_distance = float('inf')
                comp_i_size = 0.0
                comp_j_size = 0.0
                
                for comp_i in clusters[i]:
                    for comp_j in clusters[j]:
                        if comp_i in centers and comp_j in centers:
                            dist = (centers[comp_i] - centers[comp_j]).length
                            if dist < min_distance:
                                min_distance = dist
                                comp_i_size = component_sizes.get(comp_i, average_size)
                                comp_j_size = component_sizes.get(comp_j, average_size)
                
                # 2つのコンポーネントのサイズに基づいて適応的な閾値を計算
                # より大きいコンポーネントのサイズの一定割合を使用
                adaptive_threshold = max(comp_i_size, comp_j_size) * 0.5
                
                # 閾値の範囲を制限
                adaptive_threshold = max(min_threshold, min(max_threshold, adaptive_threshold))
                
                # 距離が閾値以下ならクラスターをマージ
                if min_distance <= adaptive_threshold:
                    clusters[i].extend(clusters[j])
                    clusters.pop(j)
                    merged = True
                    break
            
            if merged:
                break
    
    return clusters

# Merged from separate_and_combine_components.py

@dataclass
class ComponentInfo:
    indices: List[int]
    is_uniform: bool
    weights: Dict[str, float]
    weight_hash: str
    max_extent: float
    vertices_world: Optional[np.ndarray] = None


class _ComponentSeparationContext:
    def __init__(self, mesh_obj, clothing_armature, do_not_separate_names, clustering, clothing_avatar_data):
        self.mesh_obj = mesh_obj
        self.clothing_armature = clothing_armature
        self.do_not_separate_names = do_not_separate_names or []
        self.clustering = clustering
        self.clothing_avatar_data = clothing_avatar_data
        self.allowed_bones: Set[str] = set()
        self.non_uniform_components: List[List[int]] = []

    def prepare_allowed_bones(self):
        if not self.clothing_avatar_data:
            return

        target_humanoid_bones = ["Spine", "Chest", "Neck", "LeftBreast", "RightBreast"]
        humanoid_to_bone = {}

        if "humanoidBones" in self.clothing_avatar_data:
            for bone_data in self.clothing_avatar_data["humanoidBones"]:
                humanoid_name = bone_data.get("humanoidBoneName", "")
                bone_name = bone_data.get("boneName", "")
                if humanoid_name and bone_name:
                    humanoid_to_bone[humanoid_name] = bone_name

        for humanoid_bone in target_humanoid_bones:
            if humanoid_bone in humanoid_to_bone:
                self.allowed_bones.add(humanoid_to_bone[humanoid_bone])

        if "auxiliaryBones" in self.clothing_avatar_data:
            for aux_bone_data in self.clothing_avatar_data["auxiliaryBones"]:
                parent_humanoid = aux_bone_data.get("parentHumanoidBoneName", "")
                if parent_humanoid in target_humanoid_bones:
                    bone_name = aux_bone_data.get("boneName", "")
                    if bone_name:
                        self.allowed_bones.add(bone_name)

    def has_allowed_bone_weights(self, weights: Dict[str, float]) -> bool:
        if not self.allowed_bones:
            return True
        return any(bone_name in self.allowed_bones for bone_name in weights.keys())

    def find_components(self) -> List[List[int]]:
        components = find_connected_components(self.mesh_obj)
        if len(components) <= 1:
            return components
        print(f"Found {len(components)} connected components in {self.mesh_obj.name}")
        return components

    def analyze_components(self, components: List[List[int]]) -> List[ComponentInfo]:
        component_infos: List[ComponentInfo] = []
        weight_hash_do_not_separate: List[str] = []

        for i, component in enumerate(components):
            is_uniform, weights = check_uniform_weights(self.mesh_obj, component, self.clothing_armature)

            if is_uniform and weights:
                vertices_world = []
                for vert_idx in component:
                    vert_co = self.mesh_obj.data.vertices[vert_idx].co.copy()
                    vert_world = self.mesh_obj.matrix_world @ vert_co
                    vertices_world.append(np.array([vert_world.x, vert_world.y, vert_world.z]))

                vertices_world = np.array(vertices_world)
                _, extents = calculate_obb(vertices_world)

                if extents is not None:
                    max_extent = np.max(extents) * 2.0
                    weight_hash = generate_weight_hash(weights)

                    if max_extent < 0.0003:
                        print(f"Component {i} in {self.mesh_obj.name} is too small (max extent: {max_extent:.4f}), skipping")
                        component_infos.append(ComponentInfo(component, False, {}, "", max_extent))
                        continue

                    should_separate = True
                    temp_name = f"{self.mesh_obj.name}_Uniform_{i}"

                    for name_pattern in self.do_not_separate_names:
                        if name_pattern in temp_name:
                            should_separate = False
                            weight_hash_do_not_separate.append(weight_hash)
                            break

                    if should_separate:
                        for hash_val in weight_hash_do_not_separate:
                            if hash_val == weight_hash:
                                should_separate = False
                                break

                    if should_separate:
                        print(f"Component {i} in {self.mesh_obj.name} has uniform weights: {weight_hash} (max extent: {max_extent:.4f})")
                        component_infos.append(ComponentInfo(component, True, weights, weight_hash, max_extent, vertices_world))
                    else:
                        component_infos.append(ComponentInfo(component, False, {}, "", max_extent))
                else:
                    print(f"Component {i} in {self.mesh_obj.name} OBB calculation failed")
                    component_infos.append(ComponentInfo(component, False, {}, "", 0.0))
            else:
                print(f"Component {i} in {self.mesh_obj.name} does not have uniform weights")
                component_infos.append(ComponentInfo(component, False, {}, "", 0.0))

        return component_infos

    def group_components(self, component_infos: List[ComponentInfo]) -> Dict[str, List[Tuple[List[int], Optional[np.ndarray]]]]:
        weight_groups: Dict[str, List[Tuple[List[int], Optional[np.ndarray]]]] = {}
        non_uniform_components: List[List[int]] = []

        for info in component_infos:
            if info.is_uniform:
                weight_groups.setdefault(info.weight_hash, []).append((info.indices, info.vertices_world))
            else:
                non_uniform_components.append(info.indices)

        self.non_uniform_components = non_uniform_components
        return weight_groups

    def _duplicate_and_trim(self, keep_vertices: Set[int], name: str, copy_shape_keys: bool) -> bpy.types.Object:
        original_active = bpy.context.view_layer.objects.active

        bpy.ops.object.select_all(action='DESELECT')
        self.mesh_obj.select_set(True)
        bpy.context.view_layer.objects.active = self.mesh_obj
        bpy.ops.object.duplicate(linked=False)
        new_obj = bpy.context.active_object
        new_obj.name = name

        bpy.ops.object.select_all(action='DESELECT')
        new_obj.select_set(True)
        bpy.context.view_layer.objects.active = new_obj
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type="VERT")
        bpy.ops.mesh.select_all(action='DESELECT')

        bpy.ops.object.mode_set(mode='OBJECT')
        for i, vert in enumerate(new_obj.data.vertices):
            vert.select = i in keep_vertices

        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='INVERT')
        bpy.ops.mesh.delete(type='VERT')
        bpy.ops.object.mode_set(mode='OBJECT')

        if copy_shape_keys and self.mesh_obj.data.shape_keys:
            for key_block in self.mesh_obj.data.shape_keys.key_blocks:
                if key_block.name not in new_obj.data.shape_keys.key_blocks:
                    shape_key = new_obj.shape_key_add(name=key_block.name)
                    shape_key.value = key_block.value

        bpy.context.view_layer.objects.active = original_active
        return new_obj

    def _cluster_components(self, weight_hash: str, components_with_coords):
        component_coords = {}
        component_sizes = {}
        component_indices = {}

        for i, (component, vertices_world) in enumerate(components_with_coords):
            if vertices_world is not None and len(vertices_world) > 0:
                vectors = [Vector(v) for v in vertices_world]
                component_coords[i] = vectors
                component_sizes[i] = calculate_component_size(vectors)
                component_indices[i] = component

        clusters = cluster_components_by_adaptive_distance(component_coords, component_sizes)
        print(f"Weight hash {weight_hash} has {len(clusters)} spatial clusters")
        return clusters, component_indices

    def separate_uniform_components(self, weight_groups, component_infos: List[ComponentInfo]) -> List[bpy.types.Object]:
        uniform_objects: List[bpy.types.Object] = []

        if not self.clustering:
            return uniform_objects

        for weight_hash, components_with_coords in weight_groups.items():
            clusters, component_indices = self._cluster_components(weight_hash, components_with_coords)

            for cluster_idx, cluster in enumerate(clusters):
                first_component_id = -1
                for i, info in enumerate(component_infos):
                    if info.is_uniform and info.weight_hash == weight_hash:
                        for comp_idx in cluster:
                            if info.indices == component_indices.get(comp_idx):
                                first_component_id = i
                                break
                        if first_component_id >= 0:
                            break

                if first_component_id >= 0:
                    cluster_name = f"{self.mesh_obj.name}_Uniform_{first_component_id}_Cluster_{cluster_idx}"
                else:
                    cluster_name = f"{self.mesh_obj.name}_Uniform_Hash_{len(uniform_objects)}_Cluster_{cluster_idx}"

                should_separate = True
                for name_pattern in self.do_not_separate_names:
                    if name_pattern in cluster_name:
                        for component, _ in components_with_coords:
                            self.non_uniform_components.append(component)
                        should_separate = False
                        break
                if not should_separate:
                    continue

                keep_vertices = set()
                for comp_idx in cluster:
                    keep_vertices.update(component_indices[comp_idx])

                new_obj = self._duplicate_and_trim(keep_vertices, cluster_name, copy_shape_keys=True)
                uniform_objects.append(new_obj)

        return uniform_objects

    def build_non_uniform_object(self) -> Optional[bpy.types.Object]:
        if not self.non_uniform_components:
            return None

        keep_vertices = set()
        for component in self.non_uniform_components:
            keep_vertices.update(component)

        return self._duplicate_and_trim(keep_vertices, f"{self.mesh_obj.name}_NonUniform", copy_shape_keys=False)

    def report(self, uniform_objects: List[bpy.types.Object], non_uniform_obj: Optional[bpy.types.Object]):
        if non_uniform_obj:
            pass
        else:
            print("No non-separated object.")

        for sep_obj in uniform_objects:
            pass

def separate_and_combine_components(mesh_obj, clothing_armature, do_not_separate_names=None, clustering=True, clothing_avatar_data=None):
    """
    メッシュオブジェクト内の接続されていないコンポーネントを検出し、
    同じボーンウェイトパターンを持つものをグループ化して分離する
    """

    ctx = _ComponentSeparationContext(
        mesh_obj,
        clothing_armature,
        do_not_separate_names,
        clustering,
        clothing_avatar_data,
    )

    ctx.prepare_allowed_bones()
    components = ctx.find_components()
    if len(components) <= 1:
        return [], [mesh_obj]

    component_infos = ctx.analyze_components(components)
    weight_groups = ctx.group_components(component_infos)
    uniform_objects = ctx.separate_uniform_components(weight_groups, component_infos)
    non_uniform_obj = ctx.build_non_uniform_object()

    separated_objects = uniform_objects
    non_separated_objects = [non_uniform_obj] if non_uniform_obj else []

    ctx.report(separated_objects, non_uniform_obj)
    return separated_objects, non_separated_objects