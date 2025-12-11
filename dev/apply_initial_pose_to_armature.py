import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import json
import math

import bpy
from blender_utils.bone_utils import get_humanoid_bone_hierarchy
from io_utils.io_utils import load_avatar_data
from math_utils.geometry_utils import list_to_matrix
from mathutils import Euler, Matrix, Vector


def is_fallback_marker(path):
    """Check if path is a fallback marker (not a real file path)."""
    if not path:
        return False
    markers = ['UNUSED', 'FALLBACK', 'NONE', 'SKIP', '__']
    upper_path = path.upper()
    return any(upper_path.startswith(m) or m in upper_path for m in markers)


def apply_initial_pose_to_armature(armature_obj, init_pose_filepath, clothing_avatar_data_filepath):
    """
    Apply initial pose from JSON to the armature.
    
    Parameters:
        armature_obj: Target armature object
        init_pose_filepath: Path to initial pose JSON file, or fallback marker (e.g., 'UNUSED', '__IDENTITY__')
                           If fallback marker is provided, assumes identity matrix (no transformation)
        clothing_avatar_data_filepath: Path to avatar data JSON file
    """
    # Fallback: if marker like UNUSED, __IDENTITY__, etc. is provided,
    # assume delta_matrix is identity matrix and skip processing
    if is_fallback_marker(init_pose_filepath):
        print(f"[INFO] init_pose is fallback marker '{init_pose_filepath}', assuming identity matrix (no transformation)")
        return
    
    if not init_pose_filepath or not os.path.exists(init_pose_filepath):
        return
    
    # アバターデータを読み込む
    avatar_data = load_avatar_data(clothing_avatar_data_filepath)
    
    # 階層関係と変換マップを取得
    bone_parents, humanoid_to_bone, bone_to_humanoid = get_humanoid_bone_hierarchy(avatar_data)
    
    # 親から子への順序でHumanoidボーンを取得
    def get_bone_hierarchy_order():
        order = []
        visited = set()
        
        def add_bone_and_children(humanoid_bone):
            if humanoid_bone in visited:
                return
            visited.add(humanoid_bone)
            order.append(humanoid_bone)
            
            # 子ボーンを検索
            for child_bone, parent_bone in bone_parents.items():
                if parent_bone == humanoid_bone and child_bone not in visited:
                    add_bone_and_children(child_bone)
        
        # ルートボーン（Hips）から開始
        root_bones = []
        root_bones.append(humanoid_to_bone['Hips'])
        
        for root_bone in root_bones:
            add_bone_and_children(root_bone)
        
        return order
    
    bone_order = get_bone_hierarchy_order()
    
    # 初期ポーズの適用
    with open(init_pose_filepath, 'r', encoding='utf-8') as f:
        init_pose_data = json.load(f)

    # ボーン名をキーとしたマッピングを作成
    bone_transforms = {}
    for bone_data in init_pose_data.get("bones", []):
        bone_name = bone_data["boneName"]
        transform = bone_data["transform"]
        bone_transforms[bone_name] = transform

    # 処理済みのHumanoidボーンを記録する辞書
    processed_bones = {}

    # 事前にすべてのボーンの変形前の状態を保存
    original_bone_data = {}
    for bone_name in bone_order:
        if bone_name and bone_name in armature_obj.pose.bones:
            bone = armature_obj.pose.bones[bone_name]
            original_bone_data[bone_name] = {
                'matrix': bone.matrix.copy(),
                'head': bone.head.copy(),
                'tail': bone.tail.copy(),
            }
    
    # アーマチュアの各ボーンに初期ポーズを適用
    for bone_name in bone_order:
        if not bone_name or bone_name not in armature_obj.pose.bones:
            continue
        
        # 既に処理済みの場合はスキップ
        if bone_name in processed_bones:
            continue
        
        # 保存されたオリジナルデータを使用して計算
        if bone_name not in original_bone_data:
            continue

        if bone_name not in bone_transforms:
            continue
            
        bone = armature_obj.pose.bones[bone_name]
        
        original_data = original_bone_data[bone_name]
        
        # 現在のワールド空間での行列を取得（オリジナルデータを使用）
        current_world_matrix = armature_obj.matrix_world @ original_data['matrix']

        transform = bone_transforms[bone_name]

        # delta_matrixが存在するかチェック
        if "delta_matrix" in transform:
            # 差分変換行列を取得
            delta_matrix = list_to_matrix(transform['delta_matrix'])
            
            # 現在の行列に適用
            combined_matrix = delta_matrix @ current_world_matrix
            
            # ローカル空間に変換して適用
            bone.matrix = armature_obj.matrix_world.inverted() @ combined_matrix
        else:
            # 後方互換性のため、古い形式（position, rotation, scale）もサポート        
            # 位置を設定
            pos = transform.get("position", [0, 0, 0])
            init_loc = Vector((pos[0], pos[1], pos[2]))

            # 回転を設定（度数からラジアンに変換）
            rot = transform.get("rotation", [0, 0, 0])
            init_rot = Euler([math.radians(r) for r in rot], 'XYZ')

            # スケールを設定
            scale = transform.get("scale", [1, 1, 1])
            init_scale = Vector((scale[0], scale[1], scale[2]))

            head_world = armature_obj.matrix_world @ bone.head
            offset_matrix = Matrix.Translation(head_world)

            # 新しい行列を作成
            delta_matrix = Matrix.Translation(init_loc) @ \
                        init_rot.to_matrix().to_4x4() @ \
                        Matrix.Scale(init_scale.x, 4, (1, 0, 0)) @ \
                        Matrix.Scale(init_scale.y, 4, (0, 1, 0)) @ \
                        Matrix.Scale(init_scale.z, 4, (0, 0, 1))
            
            # 現在の行列に加算
            combined_matrix = offset_matrix @ delta_matrix @ offset_matrix.inverted() @ current_world_matrix
            
            # ローカル空間に変換して適用
            bone.matrix = armature_obj.matrix_world.inverted() @ combined_matrix
        
        # 変更を即座に反映（子ボーンの計算に影響するため）
        bpy.context.view_layer.update()
        
        # 処理済みとしてマーク
        processed_bones[bone_name] = True
    
    # ビューを更新
    bpy.context.view_layer.update()
