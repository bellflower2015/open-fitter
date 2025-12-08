import os
import sys

# Add the parent directory (extracted/) to sys.path to allow imports from sibling directories
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time

import bpy
from algo_utils.bone_group_utils import (
    get_humanoid_and_auxiliary_bone_groups,
)
from blender_utils.mesh_utils import reset_bone_weights
from create_side_weight_groups import create_side_weight_groups
from io_utils.io_utils import store_weights


def prepare_groups_and_weights(context):
    if "InpaintMask" not in context.target_obj.vertex_groups:
        context.target_obj.vertex_groups.new(name="InpaintMask")

    create_side_weight_groups(context.target_obj, context.base_avatar_data, context.clothing_armature, context.clothing_avatar_data)
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = context.target_obj

    context.original_groups = set(vg.name for vg in context.target_obj.vertex_groups)
    context.bone_groups = set(get_humanoid_and_auxiliary_bone_groups(context.base_avatar_data))

    context.original_humanoid_weights = store_weights(context.target_obj, context.bone_groups)
    context.all_deform_groups = set(context.bone_groups)
    if context.clothing_armature:
        context.all_deform_groups.update(bone.name for bone in context.clothing_armature.data.bones)

    context.original_non_humanoid_groups = context.all_deform_groups - context.bone_groups
    context.original_non_humanoid_weights = store_weights(context.target_obj, context.original_non_humanoid_groups)
    context.all_weights = store_weights(context.target_obj, context.all_deform_groups)

    reset_bone_weights(context.target_obj, context.all_deform_groups)
