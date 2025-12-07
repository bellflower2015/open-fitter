import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import json

import bpy
from algo_utils.search_utils import find_nearest_parent_with_pose
from blender_utils.bone_utils import get_humanoid_bone_hierarchy
from math_utils.transform_utils import list_to_matrix


def add_pose_from_json(armature_obj, filepath, avatar_data, invert=False):
    """
    JSONファイルから読み込んだポーズデータをアクティブなArmatureの現在のポーズに加算する
    
    Parameters:
        armature_obj: アーマチュアオブジェクト
        filepath (str): 読み込むJSONファイルのパス
        avatar_data (dict): アバターデータ
        invert (bool): 逆変換を適用するかどうか
    """
    # アクティブオブジェクトを取得
    if not armature_obj:
        raise ValueError("No active object found")
    
    if armature_obj.type != 'ARMATURE':
        raise ValueError(f"Active object '{armature_obj.name}' is not an armature")
    
    # 階層関係と変換マップを取得
    bone_parents, humanoid_to_bone, bone_to_humanoid = get_humanoid_bone_hierarchy(avatar_data)
    
    # ファイルの存在確認
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Pose data file not found: {filepath}")
    
    # JSONファイルを読み込む
    with open(filepath, 'r', encoding='utf-8') as f:
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
    
    # 処理済みのHumanoidボーンを記録する辞書
    processed_bones = {}
    
    # 事前にすべてのボーンの変形前の状態を保存
    original_bone_data = {}
    for humanoid_bone in humanoid_to_bone.keys():
        bone_name = humanoid_to_bone.get(humanoid_bone)
        if bone_name and bone_name in armature_obj.pose.bones:
            bone = armature_obj.pose.bones[bone_name]
            original_bone_data[humanoid_bone] = {
                'matrix': bone.matrix.copy(),
                'head': bone.head.copy(),
                'tail': bone.tail.copy(),
                'bone_name': bone_name
            }
    
    # 階層順序でポーズデータの計算を実行
    for bone_name in bone_order:
        if not bone_name or bone_name not in armature_obj.pose.bones:
            continue
   
        humanoid_bone = bone_to_humanoid.get(bone_name)
        if not humanoid_bone:
            continue
        
        # 既に処理済みの場合はスキップ
        if humanoid_bone in processed_bones:
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
        
        # 保存されたオリジナルデータを使用して計算
        if humanoid_bone not in original_bone_data:
            continue
            
        bone = armature_obj.pose.bones[bone_name]
        
        original_data = original_bone_data[humanoid_bone]
        
        # 現在のワールド空間での行列を取得（オリジナルデータを使用）
        current_world_matrix = armature_obj.matrix_world @ original_data['matrix']
        
        # 差分変換行列を取得
        delta_matrix = list_to_matrix(pose_data[source_humanoid_bone]['delta_matrix'])
        
        if invert:
            delta_matrix = delta_matrix.inverted()
            
        # 現在の行列に加算
        combined_matrix = delta_matrix @ current_world_matrix
        
        # ローカル空間に変換して適用
        bone.matrix = armature_obj.matrix_world.inverted() @ combined_matrix
        
        # 変更を即座に反映（子ボーンの計算に影響するため）
        bpy.context.view_layer.update()
        
        # 処理済みとしてマーク
        processed_bones[humanoid_bone] = True
    
    # 最終的なポーズの更新を強制
    bpy.context.view_layer.update()
    print(f"Pose data added to armature '{armature_obj.name}' from {filepath}")
