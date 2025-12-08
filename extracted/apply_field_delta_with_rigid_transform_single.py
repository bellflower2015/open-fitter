import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy as np
from blender_utils.deformation_utils import (
    batch_process_vertices_multi_step,
)
from blender_utils.armature_utils import get_armature_from_modifier
from math_utils.geometry_utils import (
    apply_similarity_transform_to_points,
)
from math_utils.geometry_utils import calculate_inverse_pose_matrix
from math_utils.geometry_utils import (
    calculate_optimal_similarity_transform,
)
from mathutils import Matrix, Vector
from blender_utils.deformation_utils import get_deformation_field_multi_step


def apply_field_delta_with_rigid_transform_single(obj, field_data_path, blend_shape_labels=None, clothing_avatar_data=None, shape_key_name="RigidTransformed"):
    used_shape_keys = []
    if blend_shape_labels and clothing_avatar_data:
        # 事前に作成されたシェイプキーから頂点位置を取得
        for label in blend_shape_labels:
            # 衣装モデルに同名のシェイプキーがある場合は適用しない
            if obj.data.shape_keys and label in obj.data.shape_keys.key_blocks:
                continue
            target_avatar_base_shape_key_name = f"{label}_BaseShape"
            if obj.data.shape_keys and target_avatar_base_shape_key_name in obj.data.shape_keys.key_blocks:
                target_avatar_base_shape_key = obj.data.shape_keys.key_blocks[target_avatar_base_shape_key_name]
                target_avatar_base_shape_key.value = 1.0
                used_shape_keys.append(target_avatar_base_shape_key_name)
            else:
                print(f"[Warning] Shape key {target_avatar_base_shape_key_name} not found")
    
    # 評価済みメッシュから頂点位置（元の状態）を取得
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    eval_mesh = eval_obj.data
    original_positions = np.array([v.co for v in eval_mesh.vertices])
    current_positions = original_positions.copy()
    
    # メインの Deformation Field を適用
    field_info = get_deformation_field_multi_step(field_data_path)
    field_points = field_info['all_field_points']
    delta_positions = field_info['all_delta_positions']
    field_weights = field_info['field_weights']
    field_matrix = field_info['world_matrix']
    field_matrix_inv = field_info['world_matrix_inv']
    k_neighbors = field_info['kdtree_query_k']
    
    # Deformation Field に基づく変形位置を計算
    deformed_positions = batch_process_vertices_multi_step(
        current_positions,
        field_points,
        delta_positions,
        field_weights,
        field_matrix,
        field_matrix_inv,
        obj.matrix_world,
        obj.matrix_world.inverted(),
        None,
        batch_size=1000,
        k=k_neighbors
    )
    
    # numpy配列に変換
    source_points = np.array([obj.matrix_world @ Vector(v) for v in current_positions])
    target_points = np.array(deformed_positions)

    # # DistanceWeight頂点グループからの影響度を取得
    #influence_factors = get_distance_weight_influence_factors(obj, 0.5)
    #s, R, t = calculate_optimal_similarity_transform_weighted(source_points, target_points, influence_factors)
    
    s, R, t = calculate_optimal_similarity_transform(source_points, target_points)
    
    # 相似変換を適用した結果を計算
    similarity_transformed = apply_similarity_transform_to_points(source_points, s, R, t)

    for label in used_shape_keys:
        obj.data.shape_keys.key_blocks[label].value = 0.0
    
    # シェイプキーを作成
    if obj.data.shape_keys is None:
        obj.shape_key_add(name='Basis')
    if obj.data.shape_keys and shape_key_name in obj.data.shape_keys.key_blocks:
        shape_key = obj.data.shape_keys.key_blocks[shape_key_name]
    else:
        shape_key = obj.shape_key_add(name=shape_key_name)
    shape_key.value = 1.0
    
    # アーマチュアを取得
    armature_obj = get_armature_from_modifier(obj)
    if not armature_obj:
        raise ValueError("Armatureモディファイアが見つかりません")
    
    # シェイプキーに頂点位置を設定
    matrix_armature_inv_fallback = Matrix.Identity(4)
    for i in range(len(current_positions)):
        matrix_armature_inv = calculate_inverse_pose_matrix(obj, armature_obj, i)
        if matrix_armature_inv is None:
            matrix_armature_inv = matrix_armature_inv_fallback
        undeformed_world_pos = matrix_armature_inv @ Vector(similarity_transformed[i])
        local_pos = obj.matrix_world.inverted() @ undeformed_world_pos
        shape_key.data[i].co = local_pos
        matrix_armature_inv_fallback = matrix_armature_inv
    return shape_key
