import os
import sys

# Add the parent directory (extracted/) to sys.path to allow imports from sibling directories
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy
import numpy as np


def apply_distance_falloff_blend(context):
    current_mode = bpy.context.object.mode
    bpy.context.view_layer.objects.active = context.target_obj
    bpy.ops.object.mode_set(mode="WEIGHT_PAINT")
    context.target_obj.vertex_groups.active_index = context.distance_falloff_group2.index
    humanoid_to_bone = {bone_map["humanoidBoneName"]: bone_map["boneName"] for bone_map in context.base_avatar_data["humanoidBones"]}
    exclude_bone_groups = []
    exclude_humanoid_bones = ["LeftBreast", "RightBreast"]
    for humanoid_bone in exclude_humanoid_bones:
        if humanoid_bone in humanoid_to_bone:
            exclude_bone_groups.append(humanoid_to_bone[humanoid_bone])
    for aux_set in context.base_avatar_data.get("auxiliaryBones", []):
        if aux_set["humanoidBoneName"] in exclude_humanoid_bones:
            exclude_bone_groups.extend(aux_set["auxiliaryBones"])

    if exclude_bone_groups:
        new_group_weights = np.zeros(len(context.target_obj.data.vertices), dtype=np.float32)
        for i, vertex in enumerate(context.target_obj.data.vertices):
            for group in vertex.groups:
                if group.group == context.distance_falloff_group2.index:
                    new_group_weights[i] = group.weight
                    break
        total_target_weights = np.zeros(len(context.target_obj.data.vertices), dtype=np.float32)
        for target_group_name in exclude_bone_groups:
            if target_group_name in context.target_obj.vertex_groups:
                target_group = context.target_obj.vertex_groups[target_group_name]
                for i, vertex in enumerate(context.target_obj.data.vertices):
                    for group in vertex.groups:
                        if group.group == target_group.index:
                            total_target_weights[i] += group.weight
                            break
        masked_weights = np.maximum(new_group_weights, total_target_weights)
        for i in range(len(context.target_obj.data.vertices)):
            context.distance_falloff_group2.add([i], masked_weights[i], "REPLACE")

    for vert_idx in range(len(context.target_obj.data.vertices)):
        if vert_idx in context.original_humanoid_weights and context.non_humanoid_parts_mask[vert_idx] < 0.0001:
            falloff_weight = 0.0
            for g in context.target_obj.data.vertices[vert_idx].groups:
                if g.group == context.distance_falloff_group2.index:
                    falloff_weight = g.weight
                    break
            for g in context.target_obj.data.vertices[vert_idx].groups:
                if context.target_obj.vertex_groups[g.group].name in context.bone_groups:
                    weight = g.weight
                    group_name = context.target_obj.vertex_groups[g.group].name
                    context.target_obj.vertex_groups[group_name].add([vert_idx], weight * falloff_weight, "REPLACE")
            for group_name, weight in context.original_humanoid_weights[vert_idx].items():
                if group_name in context.target_obj.vertex_groups:
                    context.target_obj.vertex_groups[group_name].add([vert_idx], weight * (1.0 - falloff_weight), "ADD")

    bpy.ops.object.mode_set(mode=current_mode)
