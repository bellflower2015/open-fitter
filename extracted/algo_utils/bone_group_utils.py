import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from blender_utils.mesh_utils import get_evaluated_mesh
from scipy.spatial import cKDTree
import bpy
import numpy as np
import os
import sys


# Merged from get_humanoid_and_auxiliary_bone_groups.py

def get_humanoid_and_auxiliary_bone_groups(base_avatar_data):
    """HumanoidボーンとAuxiliaryボーンの頂点グループを取得"""
    bone_groups = set()
    
    # Humanoidボーンを追加
    for bone_map in base_avatar_data.get("humanoidBones", []):
        if "boneName" in bone_map:
            bone_groups.add(bone_map["boneName"])
    
    # Auxiliaryボーンを追加
    for aux_set in base_avatar_data.get("auxiliaryBones", []):
        for aux_bone in aux_set.get("auxiliaryBones", []):
            bone_groups.add(aux_bone)
            
    return bone_groups

# Merged from get_deformation_bone_groups.py

def get_deformation_bone_groups(avatar_data: dict) -> list:
    """
    Get list of bone groups for deformation mask from avatar data,
    excluding Head and its auxiliary bones.
    
    Parameters:
        avatar_data: Avatar data containing bone information
        
    Returns:
        List of bone names for deformation mask
    """
    bone_groups = set()
    
    # Get mapping of humanoid bones
    for bone_map in avatar_data.get("humanoidBones", []):
        if "humanoidBoneName" in bone_map and "boneName" in bone_map:
            # Skip Head bone
            if bone_map["humanoidBoneName"] != "Head":
                bone_groups.add(bone_map["boneName"])
    
    # Get auxiliary bones mapping
    for aux_set in avatar_data.get("auxiliaryBones", []):
        humanoid_bone = aux_set["humanoidBoneName"]
        # Skip Head's auxiliary bones
        if humanoid_bone != "Head":
            aux_bones = aux_set["auxiliaryBones"]
            bone_groups.update(aux_bones)
    
    return sorted(list(bone_groups))

# Merged from create_hinge_bone_group.py

def create_hinge_bone_group(obj: bpy.types.Object, armature: bpy.types.Object, avatar_data: dict) -> None:
    """
    Create a hinge bone group.
    """
    bone_groups = get_humanoid_and_auxiliary_bone_groups(avatar_data)

    # 衣装アーマチュアのボーングループも含めた対象グループを作成
    all_deform_groups = set(bone_groups)
    if armature:
        all_deform_groups.update(bone.name for bone in armature.data.bones)

    # original_groupsからbone_groupsを除いたグループのウェイトを保存
    original_non_humanoid_groups = all_deform_groups - bone_groups

    cloth_bm = get_evaluated_mesh(obj)
    cloth_bm.verts.ensure_lookup_table()
    cloth_bm.faces.ensure_lookup_table()
    vertex_coords = np.array([v.co for v in cloth_bm.verts])
    kdtree = cKDTree(vertex_coords)

    hinge_bone_group = obj.vertex_groups.new(name="HingeBone")
    for bone_name in original_non_humanoid_groups:
        bone = armature.pose.bones.get(bone_name)
        if bone.parent and bone.parent.name in bone_groups:
            group_index = obj.vertex_groups.find(bone_name)
            if group_index != -1:
                bone_head = armature.matrix_world @ bone.head
                neighbor_indices = kdtree.query_ball_point(bone_head, 0.01)
                for index in neighbor_indices:
                    for g in obj.data.vertices[index].groups:
                        if g.group == group_index:
                            weight = g.weight
                            hinge_bone_group.add([index], weight, 'REPLACE')
                            print(f"Added weight to {index}")
                            break

# Merged from get_humanoid_and_auxiliary_bone_groups_with_intermediate.py

def get_humanoid_and_auxiliary_bone_groups_with_intermediate(base_armature: bpy.types.Object, base_avatar_data: dict) -> set:
    bone_groups = set()
    
    # まず基本のHumanoidボーンとAuxiliaryボーンを追加
    humanoid_bones = set()
    humanoid_name_to_bone = {}  # humanoidBoneName -> boneName のマッピング
    for bone_map in base_avatar_data.get("humanoidBones", []):
        if "boneName" in bone_map:
            bone_name = bone_map["boneName"]
            bone_groups.add(bone_name)
            humanoid_bones.add(bone_name)
            if "humanoidBoneName" in bone_map:
                humanoid_name_to_bone[bone_map["humanoidBoneName"]] = bone_name
    
    # Hipsボーンの実際のボーン名を取得
    hips_bone_name = humanoid_name_to_bone.get("Hips")
    
    # Auxiliaryボーンとその所属Humanoidボーンのマッピングを作成
    auxiliary_to_humanoid = {}
    humanoid_to_auxiliaries = {}
    
    for aux_set in base_avatar_data.get("auxiliaryBones", []):
        humanoid_bone_name = aux_set.get("humanoidBoneName")
        auxiliaries = aux_set.get("auxiliaryBones", [])
        
        # Humanoidボーン名から実際のボーン名を取得
        actual_humanoid_bone = None
        for bone_map in base_avatar_data.get("humanoidBones", []):
            if bone_map.get("humanoidBoneName") == humanoid_bone_name:
                actual_humanoid_bone = bone_map.get("boneName")
                break
        
        if actual_humanoid_bone:
            humanoid_to_auxiliaries[actual_humanoid_bone] = set(auxiliaries)
            for aux_bone in auxiliaries:
                bone_groups.add(aux_bone)
                auxiliary_to_humanoid[aux_bone] = actual_humanoid_bone
    
    # 中間ボーンを検出・追加
    if base_armature and base_armature.pose:
        # Humanoidボーンの親辿り処理
        for bone in base_armature.pose.bones:
            if bone.name in humanoid_bones:
                # Hipsボーンの場合は特別処理：ルートまでのすべての親ボーンを追加
                if bone.name == hips_bone_name:
                    current_parent = bone.parent
                    while current_parent:
                        bone_groups.add(current_parent.name)
                        current_parent = current_parent.parent
                else:
                    # 通常のHumanoidボーンの処理
                    # このHumanoidボーンの親を辿る
                    current_parent = bone.parent
                    intermediate_bones = []
                    
                    while current_parent:
                        if current_parent.name in humanoid_bones:
                            # 親のHumanoidボーンに到達したら、中間ボーンをすべて追加
                            bone_groups.update(intermediate_bones)
                            break
                        else:
                            # 中間ボーンとして記録
                            intermediate_bones.append(current_parent.name)
                            current_parent = current_parent.parent
        
        # Auxiliaryボーンの親辿り処理
        for aux_bone_name in auxiliary_to_humanoid.keys():
            if aux_bone_name in base_armature.pose.bones:
                bone = base_armature.pose.bones[aux_bone_name]
                parent_humanoid_bone = auxiliary_to_humanoid[aux_bone_name]
                same_group_bones = {parent_humanoid_bone} | humanoid_to_auxiliaries.get(parent_humanoid_bone, set())
                
                # このAuxiliaryボーンの親を辿る
                current_parent = bone.parent
                intermediate_bones = []
                
                while current_parent:
                    if current_parent.name in same_group_bones:
                        # 同じグループのボーンに到達したら、中間ボーンをすべて追加
                        bone_groups.update(intermediate_bones)
                        break
                    else:
                        # 中間ボーンとして記録
                        intermediate_bones.append(current_parent.name)
                        current_parent = current_parent.parent
    
    return bone_groups