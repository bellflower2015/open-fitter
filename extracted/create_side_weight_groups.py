import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import bpy
from blender_utils.bone_utils import is_left_side_bone, is_right_side_bone


def create_side_weight_groups(mesh_obj: bpy.types.Object, base_avatar_data: dict, clothing_armature: bpy.types.Object, clothing_avatar_data: dict) -> None:
   """
   右半身と左半身のウェイト合計の頂点グループを作成
   """
   # 左右のボーンを分類
   left_bones, right_bones = set(), set()
   center_bones = set()
   
   # 左右で別のグループにする脚・足・足指・胸のボーン
   leg_foot_chest_bones = {
       "LeftUpperLeg", "RightUpperLeg", "LeftLowerLeg", "RightLowerLeg",
       "LeftFoot", "RightFoot", "LeftToes", "RightToes", "LeftBreast", "RightBreast",
       "LeftFootThumbProximal", "LeftFootThumbIntermediate", "LeftFootThumbDistal",
       "LeftFootIndexProximal", "LeftFootIndexIntermediate", "LeftFootIndexDistal",
       "LeftFootMiddleProximal", "LeftFootMiddleIntermediate", "LeftFootMiddleDistal",
       "LeftFootRingProximal", "LeftFootRingIntermediate", "LeftFootRingDistal",
       "LeftFootLittleProximal", "LeftFootLittleIntermediate", "LeftFootLittleDistal",
       "RightFootThumbProximal", "RightFootThumbIntermediate", "RightFootThumbDistal",
       "RightFootIndexProximal", "RightFootIndexIntermediate", "RightFootIndexDistal",
       "RightFootMiddleProximal", "RightFootMiddleIntermediate", "RightFootMiddleDistal",
       "RightFootRingProximal", "RightFootRingIntermediate", "RightFootRingDistal",
       "RightFootLittleProximal", "RightFootLittleIntermediate", "RightFootLittleDistal"
   }
   
   # 右側グループに入れる指ボーン
   right_group_fingers = {
       "LeftThumbProximal", "LeftThumbIntermediate", "LeftThumbDistal",
       "LeftMiddleProximal", "LeftMiddleIntermediate", "LeftMiddleDistal",
       "LeftLittleProximal", "LeftLittleIntermediate", "LeftLittleDistal",
       "RightThumbProximal", "RightThumbIntermediate", "RightThumbDistal",
       "RightMiddleProximal", "RightMiddleIntermediate", "RightMiddleDistal",
       "RightLittleProximal", "RightLittleIntermediate", "RightLittleDistal"
   }
   
   # 左側グループに入れる指ボーン
   left_group_fingers = {
       "LeftIndexProximal", "LeftIndexIntermediate", "LeftIndexDistal",
       "LeftRingProximal", "LeftRingIntermediate", "LeftRingDistal",
       "RightIndexProximal", "RightIndexIntermediate", "RightIndexDistal",
       "RightRingProximal", "RightRingIntermediate", "RightRingDistal"
   }
   
   # 分離しない肩・腕・手のボーン（center_bones扱い）
   excluded_bones = {
       "LeftShoulder", "RightShoulder", "LeftUpperArm", "RightUpperArm",
       "LeftLowerArm", "RightLowerArm", "LeftHand", "RightHand"
   }

   ignored_bones = {"Head"}
   
   for bone_map in base_avatar_data.get("humanoidBones", []):
       bone_name = bone_map["boneName"]
       humanoid_name = bone_map["humanoidBoneName"]
       
       if bone_name in ignored_bones:
           continue
       if humanoid_name in excluded_bones:
           # 分離しない（center_bones扱い）
           center_bones.add(bone_name)
       elif humanoid_name in leg_foot_chest_bones:
           # 脚・足・足指・胸は従来通り左右で分ける
           if any(k in humanoid_name for k in ["Left", "left"]):
               left_bones.add(bone_name)
           elif any(k in humanoid_name for k in ["Right", "right"]):
               right_bones.add(bone_name)
       elif humanoid_name in right_group_fingers:
           # 右側グループに入れる指ボーン
           right_bones.add(bone_name)
       elif humanoid_name in left_group_fingers:
           # 左側グループに入れる指ボーン
           left_bones.add(bone_name)
       else:
           center_bones.add(bone_name)
    
   for aux_set in base_avatar_data.get("auxiliaryBones", []):
        humanoid_name = aux_set["humanoidBoneName"]
        for aux_bone in aux_set["auxiliaryBones"]:
            if humanoid_name in ignored_bones:
                continue
            if humanoid_name in excluded_bones:
                # 分離しない（center_bones扱い）
                center_bones.add(aux_bone)
            elif humanoid_name in leg_foot_chest_bones:
                # 脚・足・足指・胸は従来通り左右で分ける
                if is_left_side_bone(aux_bone, humanoid_name):
                    left_bones.add(aux_bone)
                elif is_right_side_bone(aux_bone, humanoid_name):
                    right_bones.add(aux_bone)
            elif humanoid_name in right_group_fingers:
                # 右側グループに入れる指ボーン
                right_bones.add(aux_bone)
            elif humanoid_name in left_group_fingers:
                # 左側グループに入れる指ボーン
                left_bones.add(aux_bone)
            else:
                center_bones.add(aux_bone)
   
   clothing_bone_to_humanoid = {bone_map["boneName"]: bone_map["humanoidBoneName"] 
                           for bone_map in clothing_avatar_data["humanoidBones"]}
   for clothing_bone in clothing_armature.data.bones:
        current_bone = clothing_bone
        current_bone_name = current_bone.name
        parent_humanoid_name = None
        while current_bone:
            if current_bone.name in clothing_bone_to_humanoid.keys():
                parent_humanoid_name = clothing_bone_to_humanoid[current_bone.name]
                break
            current_bone = current_bone.parent
        if parent_humanoid_name:
            if parent_humanoid_name in ignored_bones:
                continue
            if parent_humanoid_name in excluded_bones:
                # 分離しない（center_bones扱い）
                center_bones.add(current_bone_name)
            elif parent_humanoid_name in leg_foot_chest_bones:
                # 脚・足・足指・胸は従来通り左右で分ける
                if is_left_side_bone(current_bone_name, parent_humanoid_name):
                    left_bones.add(current_bone_name)
                elif is_right_side_bone(current_bone_name, parent_humanoid_name):
                    right_bones.add(current_bone_name)
            elif parent_humanoid_name in right_group_fingers:
                # 右側グループに入れる指ボーン
                right_bones.add(current_bone_name)
            elif parent_humanoid_name in left_group_fingers:
                # 左側グループに入れる指ボーン
                left_bones.add(current_bone_name)
            else:
                center_bones.add(current_bone_name)
   
   # 既存の頂点グループを取得
   vertex_groups = {vg.name: vg.index for vg in mesh_obj.vertex_groups}

   # 新しい頂点グループを作成または既存のものをクリア
   for side in ["RightSideWeights", "LeftSideWeights", "BothSideWeights"]:
       if side in mesh_obj.vertex_groups:
           mesh_obj.vertex_groups.remove(mesh_obj.vertex_groups[side])
   right_group = mesh_obj.vertex_groups.new(name="RightSideWeights")
   left_group = mesh_obj.vertex_groups.new(name="LeftSideWeights")
   both_group = mesh_obj.vertex_groups.new(name="BothSideWeights")

   # 各頂点のウェイトを計算
   for vert in mesh_obj.data.vertices:
       right_weight = 0.0
       left_weight = 0.0
       
       for g in vert.groups:
           group_name = mesh_obj.vertex_groups[g.group].name
           weight = g.weight
           
           if group_name in right_bones:
               right_weight += weight
           elif group_name in left_bones:
               left_weight += weight
           elif group_name in center_bones:
               # 中央のボーンは両方に加算
               right_weight += weight
               left_weight += weight

       # 新しい頂点グループにウェイトを設定
       if right_weight > 0:
           right_group.add([vert.index], right_weight, 'REPLACE')
       if left_weight > 0:
           left_group.add([vert.index], left_weight, 'REPLACE')
       both_group.add([vert.index], 1.0, 'REPLACE')
