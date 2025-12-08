import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy as np
from blender_utils.deformation_utils import (
    batch_process_vertices_with_custom_range,
)
from blender_utils.blendshape_utils import create_blendshape_mask
from blender_utils.armature_utils import get_armature_from_modifier
from math_utils.geometry_utils import calculate_inverse_pose_matrix
from mathutils import Matrix, Vector
from blender_utils.deformation_utils import get_deformation_field_multi_step


def apply_blendshape_deformation_fields(target_obj, field_data_path, blend_shape_labels=None, clothing_avatar_data=None, blend_shape_values=None):
    """
    BlendShape用 Deformation Field を適用し、結果を_BaseShapeがついた名前のシェイプキーとして保存する
    
    Parameters:
        target_obj: 対象メッシュオブジェクト
        field_data_path: Deformation Fieldのパス
        blend_shape_labels: 適用するブレンドシェイプのラベルリスト
        clothing_avatar_data: 衣装アバターデータ
        blend_shape_values: ブレンドシェイプの値のリスト
    """
    if not blend_shape_labels or not clothing_avatar_data:
        return
        
    # ブレンドシェイプ値の辞書を作成
    blend_shape_value_dict = {}
    if blend_shape_values:
        for i, label in enumerate(blend_shape_labels):
            if i < len(blend_shape_values):
                blend_shape_value_dict[label] = blend_shape_values[i]
            else:
                blend_shape_value_dict[label] = 1.0  # 不足している場合は1.0
    else:
        # blend_shape_valuesがNoneの場合はすべて1.0
        for label in blend_shape_labels:
            blend_shape_value_dict[label] = 1.0
    
    # オリジナルの頂点位置を取得
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = target_obj.evaluated_get(depsgraph)
    eval_mesh = eval_obj.data
    original_positions = np.array([v.co for v in eval_mesh.vertices])
    armature_obj = get_armature_from_modifier(target_obj)
    
    label_to_filepath = {}
    label_to_mask_bones = {}
    for field in clothing_avatar_data.get("invertedBlendShapeFields", []):
        label_to_filepath[field["label"]] = field["filePath"]
        if "maskBones" in field:
            label_to_mask_bones[field["label"]] = field["maskBones"]
    
    label_to_filepath_normal = {}
    label_to_mask_bones_normal = {}
    for field in clothing_avatar_data.get("blendShapeFields", []):
        label_to_filepath_normal[field["label"]] = field["filePath"]
        if "maskBones" in field:
            label_to_mask_bones_normal[field["label"]] = field["maskBones"]

    # 各ブレンドシェイプラベルに対して処理
    for label in blend_shape_labels:
        if label in label_to_filepath and (target_obj.data.shape_keys is None or label not in target_obj.data.shape_keys.key_blocks):
            blend_field_path = os.path.join(os.path.dirname(field_data_path), label_to_filepath[label])
            if os.path.exists(blend_field_path):
                start_value = 1.0 - blend_shape_value_dict[label]
                if start_value < 0.00001:
                    start_value = 0.0
                end_value = 1.0  # 終了値は常に1.0
                
                field_info_blend = get_deformation_field_multi_step(blend_field_path)
                blend_points = field_info_blend['all_field_points']
                blend_deltas = field_info_blend['all_delta_positions']
                blend_field_weights = field_info_blend['field_weights']
                blend_matrix = field_info_blend['world_matrix']
                blend_matrix_inv = field_info_blend['world_matrix_inv']
                blend_k_neighbors = field_info_blend['kdtree_query_k']
                mask_weights = None
                if label in label_to_mask_bones:
                    mask_weights = create_blendshape_mask(target_obj, label_to_mask_bones[label], clothing_avatar_data, field_name=label, store_debug_mask=True)
                    # mask_weightsがすべて0である場合は処理をスキップ
                    if mask_weights is not None and np.all(mask_weights == 0):
                        continue
                        
                # 新しいカスタムレンジ処理を使用
                world_positions = batch_process_vertices_with_custom_range(
                    original_positions,
                    blend_points,
                    blend_deltas,
                    blend_field_weights,
                    blend_matrix,
                    blend_matrix_inv,
                    target_obj.matrix_world,
                    target_obj.matrix_world.inverted(),
                    start_value,
                    end_value,
                    deform_weights=mask_weights,
                    batch_size=1000,
                    k=blend_k_neighbors
                )
                
                # シェイプキーとして保存
                shape_key_name = f"{label}_BaseShape"
                if target_obj.data.shape_keys is None:
                    target_obj.shape_key_add(name="Basis", from_mix=False)
                    
                shape_key = target_obj.shape_key_add(name=shape_key_name, from_mix=False)
                matrix_armature_inv_fallback = Matrix.Identity(4)
                for i in range(len(world_positions)):
                    matrix_armature_inv = calculate_inverse_pose_matrix(target_obj, armature_obj, i)
                    if matrix_armature_inv is None:
                        matrix_armature_inv = matrix_armature_inv_fallback
                    undeformed_world_pos = matrix_armature_inv @ Vector(world_positions[i])
                    local_pos = target_obj.matrix_world.inverted() @ undeformed_world_pos
                    shape_key.data[i].co = local_pos
                    matrix_armature_inv_fallback = matrix_armature_inv

                # 打ち消すシェイプキーを作成
                inv_shape_key = target_obj.shape_key_add(name=f"{label}_temp", from_mix=False)
                # 生成されたシェイプキーを打ち消す変位を計算して設定
                basis_key = target_obj.data.shape_keys.key_blocks["Basis"]
                if start_value < 0.00001:
                    for i in range(len(world_positions)):
                        # BaseShapeの変位を計算（現在の位置 - オリジナル位置）
                        base_displacement = Vector(shape_key.data[i].co) - Vector(basis_key.data[i].co)
                        # 打ち消すための変位（逆方向）を設定
                        inv_shape_key.data[i].co = Vector(basis_key.data[i].co) - base_displacement
                else:
                    blend_field_path = os.path.join(os.path.dirname(field_data_path), label_to_filepath_normal[label])
                    if os.path.exists(blend_field_path):
                        start_value = blend_shape_value_dict[label]
                        end_value = 1.0  # 終了値は常に1.0
                        
                        field_info_blend = get_deformation_field_multi_step(blend_field_path)
                        blend_points = field_info_blend['all_field_points']
                        blend_deltas = field_info_blend['all_delta_positions']
                        blend_field_weights = field_info_blend['field_weights']
                        blend_matrix = field_info_blend['world_matrix']
                        blend_matrix_inv = field_info_blend['world_matrix_inv']
                        blend_k_neighbors = field_info_blend['kdtree_query_k']
                        mask_weights = None
                        if label in label_to_mask_bones_normal:
                            mask_weights = create_blendshape_mask(target_obj, label_to_mask_bones_normal[label], clothing_avatar_data, field_name=label, store_debug_mask=True)
                            # mask_weightsがすべて0である場合は処理をスキップ
                            if mask_weights is not None and np.all(mask_weights == 0):
                                continue
                                
                        # 新しいカスタムレンジ処理を使用
                        world_positions = batch_process_vertices_with_custom_range(
                            original_positions,
                            blend_points,
                            blend_deltas,
                            blend_field_weights,
                            blend_matrix,
                            blend_matrix_inv,
                            target_obj.matrix_world,
                            target_obj.matrix_world.inverted(),
                            start_value,
                            end_value,
                            deform_weights=mask_weights,
                            batch_size=1000,
                            k=blend_k_neighbors
                        )

                        matrix_armature_inv_fallback = Matrix.Identity(4)
                        for i in range(len(world_positions)):
                            matrix_armature_inv = calculate_inverse_pose_matrix(target_obj, armature_obj, i)
                            if matrix_armature_inv is None:
                                matrix_armature_inv = matrix_armature_inv_fallback
                            undeformed_world_pos = matrix_armature_inv @ Vector(world_positions[i])
                            local_pos = target_obj.matrix_world.inverted() @ undeformed_world_pos
                            base_displacement = Vector(shape_key.data[i].co) - Vector(basis_key.data[i].co)
                            inv_shape_key.data[i].co = local_pos - base_displacement
                            matrix_armature_inv_fallback = matrix_armature_inv

            else:
                print(f"[Warning] Field file not found for blend shape {label}")
        else:
            print(f"[Warning] No field data found for blend shape {label}")
