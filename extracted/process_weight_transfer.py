import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import time

from blender_utils.bone_utils import build_bone_maps
from stages.adjust_hands_and_propagate import adjust_hands_and_propagate
from stages.apply_distance_falloff_blend import apply_distance_falloff_blend
from stages.apply_metadata_fallback import apply_metadata_fallback
from stages.blend_results import blend_results
from stages.compare_side_and_bone_weights import compare_side_and_bone_weights
from stages.compute_non_humanoid_masks import compute_non_humanoid_masks
from stages.constants import (
    FINGER_HUMANOID_BONES,
    LEFT_FOOT_FINGER_HUMANOID_BONES,
    RIGHT_FOOT_FINGER_HUMANOID_BONES,
)
from stages.create_closing_filter_mask import create_closing_filter_mask
from stages.detect_finger_vertices import detect_finger_vertices
from stages.merge_added_groups import merge_added_groups
from stages.prepare_groups_and_weights import prepare_groups_and_weights
from stages.process_mf_group import process_mf_group
from stages.restore_head_weights import restore_head_weights
from stages.run_distance_normal_smoothing import run_distance_normal_smoothing
from stages.smooth_and_cleanup import smooth_and_cleanup
from stages.store_intermediate_results import store_intermediate_results
from stages.transfer_side_weights import transfer_side_weights


class WeightTransferContext:
    """Stateful context to orchestrate weight transfer without changing external IO."""

    def __init__(self, target_obj, armature, base_avatar_data, clothing_avatar_data, field_path, clothing_armature, cloth_metadata=None):
        self.target_obj = target_obj
        self.armature = armature
        self.base_avatar_data = base_avatar_data
        self.clothing_avatar_data = clothing_avatar_data
        self.field_path = field_path
        self.clothing_armature = clothing_armature
        self.cloth_metadata = cloth_metadata
        self.start_time = time.time()

        self.humanoid_to_bone = {}
        self.bone_to_humanoid = {}
        self.auxiliary_bones = {}
        self.auxiliary_bones_to_humanoid = {}
        self.finger_humanoid_bones = FINGER_HUMANOID_BONES
        self.left_foot_finger_humanoid_bones = LEFT_FOOT_FINGER_HUMANOID_BONES
        self.right_foot_finger_humanoid_bones = RIGHT_FOOT_FINGER_HUMANOID_BONES

        self.finger_bone_names = set()
        self.finger_vertices = set()
        self.closing_filter_mask_weights = None
        self.original_groups = set()
        self.bone_groups = set()
        self.all_deform_groups = set()
        self.original_non_humanoid_groups = set()
        self.original_humanoid_weights = {}
        self.original_non_humanoid_weights = {}
        self.all_weights = {}
        self.new_groups = set()
        self.added_groups = set()
        self.non_humanoid_parts_mask = None
        self.non_humanoid_total_weights = None
        self.non_humanoid_difference_mask = None
        self.distance_falloff_group = None
        self.distance_falloff_group2 = None
        self.non_humanoid_difference_group = None
        self.weights_a = {}
        self.weights_b = {}

    def run(self):
        (
            self.humanoid_to_bone,
            self.bone_to_humanoid,
            self.auxiliary_bones,
            self.auxiliary_bones_to_humanoid,
        ) = build_bone_maps(self.base_avatar_data)
        detect_finger_vertices(self)
        create_closing_filter_mask(self)
        prepare_groups_and_weights(self)
        if not transfer_side_weights(self):
            return
        process_mf_group(self, "MF_Armpit", "WT_shape_forA.MFTemp", 45, "LeftUpperArm", "RightUpperArm")
        process_mf_group(self, "MF_crotch", "WT_shape_forCrotch.MFTemp", 70, "LeftUpperLeg", "RightUpperLeg")
        smooth_and_cleanup(self)
        compute_non_humanoid_masks(self)
        merge_added_groups(self)
        store_intermediate_results(self)
        blend_results(self)
        adjust_hands_and_propagate(self)
        compare_side_and_bone_weights(self)
        run_distance_normal_smoothing(self)
        apply_distance_falloff_blend(self)
        restore_head_weights(self)
        apply_metadata_fallback(self)
        total_time = time.time() - self.start_time

def process_weight_transfer(target_obj, armature, base_avatar_data, clothing_avatar_data, field_path, clothing_armature, cloth_metadata=None):
    """Orchestrator that delegates weight transfer to a stateful context."""
    context = WeightTransferContext(
        target_obj=target_obj,
        armature=armature,
        base_avatar_data=base_avatar_data,
        clothing_avatar_data=clothing_avatar_data,
        field_path=field_path,
        clothing_armature=clothing_armature,
        cloth_metadata=cloth_metadata,
    )
    context.run()
