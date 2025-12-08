import os
import sys

# Add the parent directory (extracted/) to sys.path to allow imports from sibling directories
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time

import bpy
from blender_utils.mesh_utils import reset_bone_weights
from io_utils.io_utils import restore_weights
from stages.attempt_weight_transfer import attempt_weight_transfer


def transfer_side_weights(context):
    left_transfer_success, left_distance_used = attempt_weight_transfer(
        context, bpy.data.objects["Body.BaseAvatar.LeftOnly"], "LeftSideWeights"
    )
    if not left_transfer_success:
        reset_bone_weights(context.target_obj, context.bone_groups)
        restore_weights(context.target_obj, context.all_weights)
        return False

    right_transfer_success, right_distance_used = attempt_weight_transfer(
        context, bpy.data.objects["Body.BaseAvatar.RightOnly"], "RightSideWeights", max_distance_tried=left_distance_used
    )
    if not right_transfer_success:
        reset_bone_weights(context.target_obj, context.bone_groups)
        restore_weights(context.target_obj, context.all_weights)
        return False
    return True
