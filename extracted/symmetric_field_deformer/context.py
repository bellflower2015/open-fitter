"""
SymmetricFieldDeformerContext - 対称変形処理の状態を管理するコンテキストクラス
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from blender_utils.blendshape_utils import TransitionCache


class SymmetricFieldDeformerContext:
    """
    保存された対称Deformation Field差分データを読み込みメッシュに適用する際の
    状態（コンテキスト）を保持するクラス。
    """

    def __init__(
        self,
        target_obj,
        field_data_path,
        blend_shape_labels=None,
        clothing_avatar_data=None,
        base_avatar_data=None,
        subdivision=True,
        shape_key_name="SymmetricDeformed",
        skip_blend_shape_generation=False,
        config_data=None,
        ignore_blendshape=None,
    ):
        # 入力パラメータ
        self.target_obj = target_obj
        self.field_data_path = field_data_path
        self.blend_shape_labels = blend_shape_labels
        self.clothing_avatar_data = clothing_avatar_data
        self.base_avatar_data = base_avatar_data
        self.subdivision = subdivision
        self.shape_key_name = shape_key_name
        self.skip_blend_shape_generation = skip_blend_shape_generation
        self.config_data = config_data
        self.ignore_blendshape = ignore_blendshape

        # 共有状態
        self.transition_cache = TransitionCache()
        self.deferred_transitions = []
        self.config_blend_shape_labels = set()
        self.config_generated_shape_keys = {}
        self.additional_shape_keys = set()
        self.non_relative_shape_keys = set()
        self.label_to_target_shape_key_name = {"Basis": shape_key_name}
        self.shape_key = None
        self.non_transitioned_shape_vertices = None
        self.created_shape_key_mask_weights = {}
        self.shape_keys_to_remove = []
