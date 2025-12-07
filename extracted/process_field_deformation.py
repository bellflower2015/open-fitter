import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy as np
from blender_utils.batch_process_vertices_multi_step import (
    batch_process_vertices_multi_step,
)
from blender_utils.armature_utils import get_armature_from_modifier
from math_utils.transform_utils import calculate_inverse_pose_matrix
from mathutils import Matrix, Vector
from misc_utils.get_deformation_field_multi_step import get_deformation_field_multi_step


def process_field_deformation(target_obj, field_data_path, blend_shape_labels=None, clothing_avatar_data=None, shape_key_name="SymmetricDeformed", ignore_blendshape=None, target_shape_key=None, base_shape_key=None):
    # ① 評価済みメッシュから頂点位置（元の状態）を取得
    if target_shape_key is not None:
        # すべてのシェイプキーの値を0に設定
        for sk in target_obj.data.shape_keys.key_blocks:
            sk.value = 0.0
        # 対象のシェイプキーの値を1に設定
        target_shape_key.value = 1.0
    
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj_original = target_obj.evaluated_get(depsgraph)
    eval_mesh_original = eval_obj_original.data
    original_positions = np.array([v.co for v in eval_mesh_original.vertices])
    
    used_shape_keys = []
    if ignore_blendshape is None or ignore_blendshape is False:
        if blend_shape_labels and clothing_avatar_data:
            # 事前に作成されたシェイプキーから頂点位置を取得
            for label in blend_shape_labels:
                # ignore_blendshapeがNoneの場合は自動判別。衣装モデルに同名のシェイプキーがある場合は適用しない
                if ignore_blendshape is None and target_obj.data.shape_keys and label in target_obj.data.shape_keys.key_blocks:
                    print(f"Skipping {label} - already has shape key")
                    continue
                target_avatar_base_shape_key_name = f"{label}_BaseShape"
                if target_obj.data.shape_keys and target_avatar_base_shape_key_name in target_obj.data.shape_keys.key_blocks:
                    target_avatar_base_shape_key = target_obj.data.shape_keys.key_blocks[target_avatar_base_shape_key_name]
                    target_avatar_base_shape_key.value = 1.0
                    print(f"Using shape key {target_avatar_base_shape_key_name} for BlendShape deformation")
                    used_shape_keys.append(target_avatar_base_shape_key_name)
                else:
                    print(f"Warning: Shape key {target_avatar_base_shape_key_name} not found")

    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = target_obj.evaluated_get(depsgraph)
    eval_mesh = eval_obj.data
    # blend_positions には BlendShape適用後の頂点位置が入る
    blend_positions = np.array([v.co for v in eval_mesh.vertices])
    
    # ③ メインの Deformation Field 情報を取得
    field_info = get_deformation_field_multi_step(field_data_path)
    field_points = field_info['all_field_points']
    delta_positions = field_info['all_delta_positions']
    field_weights = field_info['field_weights']
    field_matrix = field_info['world_matrix']
    field_matrix_inv = field_info['world_matrix_inv']
    k_neighbors = field_info['kdtree_query_k']
    
    final_positions = batch_process_vertices_multi_step(
        blend_positions,
        field_points,
        delta_positions,
        field_weights,
        field_matrix,
        field_matrix_inv,
        target_obj.matrix_world,
        target_obj.matrix_world.inverted(),
        None,
        batch_size=1000,
        k=k_neighbors
    )

    for label in used_shape_keys:
        target_obj.data.shape_keys.key_blocks[label].value = 0.0
    
    armature_obj = get_armature_from_modifier(target_obj)
    if not armature_obj:
        raise ValueError("Armatureモディファイアが見つかりません")
    
    # ⑩ シェイプキーの保存または差分計算
    if target_shape_key is not None and base_shape_key is not None:
        # 差分計算モード: base_shape_keyからの差分を計算してtarget_shape_keyに保存
        matrix_armature_inv_fallback = Matrix.Identity(4)
        for i in range(len(original_positions)):
            matrix_armature_inv = calculate_inverse_pose_matrix(target_obj, armature_obj, i)
            if matrix_armature_inv is None:
                matrix_armature_inv = matrix_armature_inv_fallback
            undeformed_world_pos = matrix_armature_inv @ Vector(final_positions[i])
            local_pos = target_obj.matrix_world.inverted() @ undeformed_world_pos
            
            # base_shape_keyからの差分を計算
            base_pos = base_shape_key.data[i].co
            delta = local_pos - base_pos
            
            # 差分をtarget_shape_keyに保存
            target_shape_key.data[i].co = target_obj.data.vertices[i].co + delta
            matrix_armature_inv_fallback = matrix_armature_inv
        return target_shape_key
    else:
        # 通常モード: 新しいシェイプキーを作成して保存
        matrix_armature_inv_fallback = Matrix.Identity(4)
        if target_obj.data.shape_keys is None:
            target_obj.shape_key_add(name='Basis')
        shape_key_a = target_obj.shape_key_add(name=shape_key_name)
        shape_key_a.value = 1.0
        
        for i in range(len(original_positions)):
            matrix_armature_inv = calculate_inverse_pose_matrix(target_obj, armature_obj, i)
            if matrix_armature_inv is None:
                matrix_armature_inv = matrix_armature_inv_fallback
            undeformed_world_pos = matrix_armature_inv @ Vector(final_positions[i])
            local_pos = target_obj.matrix_world.inverted() @ undeformed_world_pos
            shape_key_a.data[i].co = local_pos
            matrix_armature_inv_fallback = matrix_armature_inv
        return shape_key_a
