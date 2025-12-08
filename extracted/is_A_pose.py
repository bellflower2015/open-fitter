import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import json
import math

import bpy
from add_pose_from_json import add_pose_from_json
from apply_initial_pose_to_armature import apply_initial_pose_to_armature
from mathutils import Vector


def is_A_pose(avatar_data: dict, armature: bpy.types.Object, init_pose_filepath=None, pose_filepath=None, clothing_avatar_data_filepath=None) -> bool:
    """
    Check if the avatar data is in A pose.
    Creates a temporary copy of the armature, applies initial pose, checks A-pose, then deletes the copy.
    
    Parameters:
        avatar_data: Avatar data dictionary
        armature: Target armature object
        init_pose_filepath: Path to initial pose JSON file (optional)
        clothing_avatar_data_filepath: Path to avatar data JSON file (optional)
    """
    # 一時的にarmatureをコピー
    original_active = bpy.context.view_layer.objects.active
    original_mode = armature.mode if hasattr(armature, 'mode') else 'OBJECT'
    
    # オブジェクトモードに切り替え
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    
    # 選択を解除
    bpy.ops.object.select_all(action='DESELECT')
    
    # アーマチュアをコピー
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.duplicate()
    temp_armature = bpy.context.active_object
    temp_armature.name = f"{armature.name}_temp_A_pose_check"
    
    try:
        # 初期ポーズを適用
        if init_pose_filepath and clothing_avatar_data_filepath:
            apply_initial_pose_to_armature(temp_armature, init_pose_filepath, clothing_avatar_data_filepath)
        
        if pose_filepath and clothing_avatar_data_filepath:
            with open(clothing_avatar_data_filepath, 'r', encoding='utf-8') as f:
                clothing_avatar_data = json.load(f)
            add_pose_from_json(temp_armature, pose_filepath, clothing_avatar_data, invert=False)
        
        # Create mappings for clothing
        humanoid_to_bone = {}
        for bone_map in avatar_data.get("humanoidBones", []):
            if "humanoidBoneName" in bone_map and "boneName" in bone_map:
                humanoid_to_bone[bone_map["humanoidBoneName"]] = bone_map["boneName"]
        
        arm_bone = None
        lower_arm_bone = None
        for bone in temp_armature.pose.bones:   
            if bone.name == humanoid_to_bone.get("LeftUpperArm"):
                for bone2 in temp_armature.pose.bones:
                    if bone2.name == humanoid_to_bone.get("LeftLowerArm"):
                        lower_arm_bone = bone2
                        break
                if lower_arm_bone:
                    arm_bone = bone
                    break
            elif bone.name == humanoid_to_bone.get("RightUpperArm"):
                for bone2 in temp_armature.pose.bones:
                    if bone2.name == humanoid_to_bone.get("RightLowerArm"):
                        lower_arm_bone = bone2
                        break
                if lower_arm_bone:
                    arm_bone = bone
                    break

        result = False
        if arm_bone and lower_arm_bone:
            arm_bone_direction = (temp_armature.matrix_world @ lower_arm_bone.head) - (temp_armature.matrix_world @ arm_bone.head)
            arm_bone_direction = arm_bone_direction.normalized()
            arm_bone_angle = math.acos(abs(arm_bone_direction.dot(Vector((1, 0, 0)))))
            if math.degrees(arm_bone_angle) > 30:
                result = True
            else:
                result = False
        else:
            result = False
    
    finally:
        # 一時的なarmatureを削除
        bpy.ops.object.select_all(action='DESELECT')
        temp_armature.select_set(True)
        bpy.context.view_layer.objects.active = temp_armature
        bpy.ops.object.delete()
        
        # 元のアクティブオブジェクトを復元
        if original_active:
            bpy.context.view_layer.objects.active = original_active
    
    return result
