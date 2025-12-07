import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import time

from blender_utils.build_bone_maps import build_bone_maps
from stages.compute_non_humanoid_masks import compute_non_humanoid_masks
from stages.merge_added_groups import merge_added_groups
from stages.run_distance_normal_smoothing import run_distance_normal_smoothing
from stages.apply_distance_falloff_blend import apply_distance_falloff_blend
from stages.restore_head_weights import restore_head_weights
from stages.apply_metadata_fallback import apply_metadata_fallback
from stages.compare_side_and_bone_weights import compare_side_and_bone_weights
from stages.detect_finger_vertices import detect_finger_vertices
from stages.create_closing_filter_mask import create_closing_filter_mask
from stages.prepare_groups_and_weights import prepare_groups_and_weights
from stages.attempt_weight_transfer import attempt_weight_transfer
from stages.transfer_side_weights import transfer_side_weights
from stages.smooth_and_cleanup import smooth_and_cleanup
from stages.store_intermediate_results import store_intermediate_results
from stages.blend_results import blend_results
from stages.adjust_hands_and_propagate import adjust_hands_and_propagate
from stages.process_mf_group import process_mf_group
from stages.constants import (
    FINGER_HUMANOID_BONES,
    LEFT_FOOT_FINGER_HUMANOID_BONES,
    RIGHT_FOOT_FINGER_HUMANOID_BONES,
)


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

    def _build_bone_maps(self):
        """ヒューマノイドボーンと補助ボーンのマッピングを構築する。"""
        (
            self.humanoid_to_bone,
            self.bone_to_humanoid,
            self.auxiliary_bones,
            self.auxiliary_bones_to_humanoid,
        ) = build_bone_maps(self.base_avatar_data)

    def detect_finger_vertices(self):
        detect_finger_vertices(self)

    def create_closing_filter_mask(self):
        create_closing_filter_mask(self)

    def attempt_weight_transfer(self, source_obj, vertex_group, max_distance_try=0.2, max_distance_tried=0.0):
        return attempt_weight_transfer(self, source_obj, vertex_group, max_distance_try, max_distance_tried)



    def prepare_groups_and_weights(self):
        prepare_groups_and_weights(self)

    def transfer_side_weights(self):
        return transfer_side_weights(self)

    def _process_mf_group(self, group_name, temp_shape_name, rotation_deg, humanoid_label_left, humanoid_label_right):
        process_mf_group(self, group_name, temp_shape_name, rotation_deg, humanoid_label_left, humanoid_label_right)

    def run_armpit_process(self):
        self._process_mf_group("MF_Armpit", "WT_shape_forA.MFTemp", 45, "LeftUpperArm", "RightUpperArm")

    def run_crotch_process(self):
        self._process_mf_group("MF_crotch", "WT_shape_forCrotch.MFTemp", 70, "LeftUpperLeg", "RightUpperLeg")

    def smooth_and_cleanup(self):
        smooth_and_cleanup(self)

    def compute_non_humanoid_masks(self):
        compute_non_humanoid_masks(self)

    def merge_added_groups(self):
        merge_added_groups(self)

    def store_intermediate_results(self):
        store_intermediate_results(self)

    def blend_results(self):
        blend_results(self)

    def adjust_hands_and_propagate(self):
        adjust_hands_and_propagate(self)

    def compare_side_and_bone_weights(self):
        compare_side_and_bone_weights(self)

    def run_distance_normal_smoothing(self):
        run_distance_normal_smoothing(self)

    def apply_distance_falloff_blend(self):
        apply_distance_falloff_blend(self)

    def restore_head_weights(self):
        restore_head_weights(self)

    def apply_metadata_fallback(self):
        apply_metadata_fallback(self)

    def run(self):
        print(f"処理開始: {self.target_obj.name}")
        self._build_bone_maps()
        self.detect_finger_vertices()
        self.create_closing_filter_mask()
        self.prepare_groups_and_weights()
        if not self.transfer_side_weights():
            return
        self.run_armpit_process()
        self.run_crotch_process()
        self.smooth_and_cleanup()
        self.compute_non_humanoid_masks()
        self.merge_added_groups()
        self.store_intermediate_results()
        self.blend_results()
        self.adjust_hands_and_propagate()
        self.compare_side_and_bone_weights()
        self.run_distance_normal_smoothing()
        self.apply_distance_falloff_blend()
        self.restore_head_weights()
        self.apply_metadata_fallback()
        total_time = time.time() - self.start_time
        print(f"処理完了: {self.target_obj.name} - 合計時間: {total_time:.2f}秒")


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
