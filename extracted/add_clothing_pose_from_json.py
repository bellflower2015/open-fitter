import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import json

import bpy
from algo_utils.search_utils import find_nearest_parent_with_pose
from apply_initial_pose_to_armature import apply_initial_pose_to_armature
from blender_utils.clear_humanoid_bone_relations_preserve_pose import (
    clear_humanoid_bone_relations_preserve_pose,
)
from blender_utils.bone_utils import get_humanoid_bone_hierarchy
from io_utils.avatar_data import load_avatar_data
from io_utils.pose_state import store_pose_globally
from math_utils.transform_utils import list_to_matrix


def add_clothing_pose_from_json(armature_obj, pose_filepath="pose_data.json", init_pose_filepath="initial_pose.json", clothing_avatar_data_filepath="avatar_data.json", base_avatar_data_filepath="avatar_data.json", invert=False):
    """
    JSONファイルから読み込んだポーズデータをアクティブなArmatureの現在のポーズに加算する
    
    Parameters:
        filename (str): 読み込むJSONファイルの名前
        avatar_data_file (str): アバターデータのJSONファイル名
        invert (bool): 逆変換を適用するかどうか
    """
    
    if not armature_obj:
        raise ValueError("No active object found")
    
    if armature_obj.type != 'ARMATURE':
        raise ValueError(f"Active object '{armature_obj.name}' is not an armature")
    
    # アバターデータを読み込む
    avatar_data = load_avatar_data(clothing_avatar_data_filepath)
    
    # 階層関係と変換マップを取得
    bone_parents, humanoid_to_bone, bone_to_humanoid = get_humanoid_bone_hierarchy(avatar_data)
    
    # ファイルの存在確認
    if not os.path.exists(pose_filepath):
        raise FileNotFoundError(f"Pose data file not found: {pose_filepath}")
    
    # JSONファイルを読み込む
    with open(pose_filepath, 'r', encoding='utf-8') as f:
        pose_data = json.load(f)
    
    # アンドゥ用にステップを作成
    bpy.ops.ed.undo_push(message="Add Pose from JSON")

    bpy.ops.object.mode_set(mode='OBJECT')
    # すべての選択を解除
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = armature_obj
    
    # エディットモードに切り替え
    bpy.ops.object.mode_set(mode='EDIT')
    
    # すべての編集ボーンのConnectedを解除
    for bone in armature_obj.data.edit_bones:
        bone.use_connect = False
    
    # オブジェクトモードに戻る
    bpy.ops.object.mode_set(mode='OBJECT')

    # 親子関係を維持したまま処理するため、階層順序でボーンを取得
    def get_bone_hierarchy_order():
        """親から子への順序でHumanoidボーンを取得"""
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
    
    # Humanoidボーンの親子関係を解除
    clear_humanoid_bone_relations_preserve_pose(armature_obj, clothing_avatar_data_filepath, base_avatar_data_filepath)
    
    bpy.context.view_layer.update()

    # ポーズを適用する前に現在のポーズを記録
    store_pose_globally(armature_obj)
    print(f"Pose state stored globally before applying pose from {pose_filepath}")

    # 初期ポーズの適用（新しい独立した関数を使用）
    if init_pose_filepath:
        apply_initial_pose_to_armature(armature_obj, init_pose_filepath, clothing_avatar_data_filepath)
    
    # 処理済みのHumanoidボーンを記録する辞書
    processed_bones = {}
    
    # ポーズデータを現在のポーズに加算
    for humanoid_bone in bone_to_humanoid.values():
        # 既に処理済みの場合はスキップ
        if humanoid_bone in processed_bones:
            continue

        if humanoid_bone == "UpperChest" or \
           humanoid_bone == "LeftBreast" or humanoid_bone == "RightBreast" or \
           humanoid_bone == "LeftToes" or humanoid_bone == "RightToes":
            continue
            
        bone_name = humanoid_to_bone.get(humanoid_bone)
        if not bone_name or bone_name not in armature_obj.pose.bones:
            continue

        # ポーズデータを直接持っているか、親から継承するかを決定
        source_humanoid_bone = humanoid_bone
        if humanoid_bone not in pose_data:
            parent_with_pose = find_nearest_parent_with_pose(
                bone_name, bone_parents, bone_to_humanoid, pose_data)
            if not parent_with_pose:
                continue
            source_humanoid_bone = parent_with_pose
            print(f"Using pose data from parent bone {source_humanoid_bone} for {humanoid_bone}")
        
        # ポーズデータを適用
        bone = armature_obj.pose.bones[bone_name]
        
        # 現在のワールド空間での行列を取得
        current_world_matrix = armature_obj.matrix_world @ bone.matrix
        
        # 差分変換行列を取得
        delta_matrix = list_to_matrix(pose_data[source_humanoid_bone]['delta_matrix'])
                    
        if invert:
            delta_matrix = delta_matrix.inverted()
            
        # 現在の行列に加算
        combined_matrix = delta_matrix @ current_world_matrix
        
        # ローカル空間に変換して適用
        bone.matrix = armature_obj.matrix_world.inverted() @ combined_matrix
        
        # 処理済みとしてマーク
        processed_bones[humanoid_bone] = True
    
    # ポーズの更新を強制
    bpy.context.view_layer.update()
    print(f"Pose data added to armature '{armature_obj.name}' from {pose_filepath}")
    
    for bone_name in armature_obj.pose.bones.keys():
        if bone_name in bone_to_humanoid:
            humanoid_name = bone_to_humanoid[bone_name]
            if humanoid_name in processed_bones:
                mat = armature_obj.pose.bones[bone_name].matrix
                print(f"'{humanoid_name}' ({bone_name}) bone.matrix_final {mat}")
