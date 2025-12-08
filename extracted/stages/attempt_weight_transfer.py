import os
import sys

# Add the parent directory (extracted/) to sys.path to allow imports from sibling directories
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy
from algo_utils.bone_group_utils import (
    get_humanoid_and_auxiliary_bone_groups,
)
from create_distance_normal_based_vertex_group import (
    create_distance_normal_based_vertex_group,
)
from io_utils.io_utils import restore_weights, store_weights


def attempt_weight_transfer(context, source_obj, vertex_group, max_distance_try=0.2, max_distance_tried=0.0):
    bone_groups_tmp = get_humanoid_and_auxiliary_bone_groups(context.base_avatar_data)
    prev_weights = store_weights(context.target_obj, bone_groups_tmp)
    initial_max_distance = max_distance_try

    while max_distance_try <= 1.0:
        if max_distance_tried + 0.0001 < max_distance_try:
            create_distance_normal_based_vertex_group(
                bpy.data.objects["Body.BaseAvatar"],
                context.target_obj,
                max_distance_try,
                0.005,
                20.0,
                "InpaintMask",
                normal_radius=0.003,
                filter_mask=context.closing_filter_mask_weights,
            )

            if context.finger_vertices:
                for vert_idx in context.finger_vertices:
                    context.target_obj.vertex_groups["InpaintMask"].add([vert_idx], 0.0, "REPLACE")

            if "MF_Inpaint" in context.target_obj.vertex_groups and "InpaintMask" in context.target_obj.vertex_groups:
                inpaint_group = context.target_obj.vertex_groups["InpaintMask"]
                source_group = context.target_obj.vertex_groups["MF_Inpaint"]

                for vert in context.target_obj.data.vertices:
                    source_weight = 0.0
                    for g in vert.groups:
                        if g.group == source_group.index:
                            source_weight = g.weight
                            break
                    inpaint_weight = 0.0
                    for g in vert.groups:
                        if g.group == inpaint_group.index:
                            inpaint_weight = g.weight
                            break
                    inpaint_group.add([vert.index], source_weight * inpaint_weight, "REPLACE")

            if "InpaintMask" in context.target_obj.vertex_groups and vertex_group in context.target_obj.vertex_groups:
                inpaint_group = context.target_obj.vertex_groups["InpaintMask"]
                source_group = context.target_obj.vertex_groups[vertex_group]

                for vert in context.target_obj.data.vertices:
                    source_weight = 0.0
                    for g in vert.groups:
                        if g.group == source_group.index:
                            source_weight = g.weight
                            break
                    if source_weight == 0.0:
                        inpaint_group.add([vert.index], 0.0, "REPLACE")

        try:
            bpy.context.scene.robust_weight_transfer_settings.source_object = source_obj
            bpy.context.object.robust_weight_transfer_settings.vertex_group = vertex_group
            bpy.context.scene.robust_weight_transfer_settings.inpaint_mode = "POINT"
            bpy.context.scene.robust_weight_transfer_settings.max_distance = max_distance_try
            bpy.context.scene.robust_weight_transfer_settings.use_deformed_target = True
            bpy.context.scene.robust_weight_transfer_settings.use_deformed_source = True
            bpy.context.scene.robust_weight_transfer_settings.enforce_four_bone_limit = True
            bpy.context.scene.robust_weight_transfer_settings.max_normal_angle_difference = 1.5708
            bpy.context.scene.robust_weight_transfer_settings.flip_vertex_normal = True
            bpy.context.scene.robust_weight_transfer_settings.smoothing_enable = False
            bpy.context.scene.robust_weight_transfer_settings.smoothing_repeat = 4
            bpy.context.scene.robust_weight_transfer_settings.smoothing_factor = 0.5
            bpy.context.object.robust_weight_transfer_settings.inpaint_group = "InpaintMask"
            bpy.context.object.robust_weight_transfer_settings.inpaint_threshold = 0.5
            bpy.context.object.robust_weight_transfer_settings.inpaint_group_invert = False
            bpy.context.object.robust_weight_transfer_settings.vertex_group_invert = False
            bpy.context.scene.robust_weight_transfer_settings.group_selection = "DEFORM_POSE_BONES"
            bpy.ops.object.skin_weight_transfer()
            print(f"Weight transfered with max_distance {max_distance_try}")
            return True, max_distance_try
        except RuntimeError as exc:
            restore_weights(context.target_obj, prev_weights)
            max_distance_try += 0.05
            if max_distance_try > 1.0:
                print("Max distance exceeded 1.0, stopping weight transfer attempts")
                return False, initial_max_distance
    return False, initial_max_distance
