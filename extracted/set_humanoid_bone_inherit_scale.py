import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import bpy
from blender_utils.bone_utils import get_humanoid_bone_hierarchy


def set_humanoid_bone_inherit_scale(armature_obj: bpy.types.Object, avatar_data: dict) -> None:
    
    print("set_humanoid_bone_inherit_scale")
    
    # Humanoidボーンの情報を取得
    bone_parents, humanoid_to_bone, bone_to_humanoid = get_humanoid_bone_hierarchy(avatar_data)
    
    # EditModeに切り替え
    bpy.context.view_layer.objects.active = armature_obj
    bpy.ops.object.mode_set(mode='EDIT')
    
    modified_count = 0
    
    # 各Humanoidボーンに対してInherit Scaleを設定
    for humanoid_bone_name, bone_name in humanoid_to_bone.items():
        if bone_name in armature_obj.data.edit_bones:
            edit_bone = armature_obj.data.edit_bones[bone_name]
            
            # Inherit ScaleがNone以外の場合のみ設定
            if edit_bone.inherit_scale != 'NONE':
                # UpperChest、胸、つま先、足の指のヒューマノイドボーンはFullに設定
                if 'Breast' in humanoid_bone_name or 'UpperChest' in humanoid_bone_name or 'Toe' in humanoid_bone_name or ('Foot' in humanoid_bone_name and ('Index' in humanoid_bone_name or 'Little' in humanoid_bone_name or 'Middle' in humanoid_bone_name or 'Ring' in humanoid_bone_name or 'Thumb' in humanoid_bone_name)):
                    edit_bone.inherit_scale = 'FULL'
                else:
                    edit_bone.inherit_scale = 'AVERAGE'
                modified_count += 1
    
    # ObjectModeに戻る
    bpy.ops.object.mode_set(mode='OBJECT')
