"""PoseFinalizationStage: ポーズ適用・ボーン調整・変換適用・ウェイトクリーンアップを担当するステージ"""

import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

_CURR_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT_DIR = os.path.dirname(_CURR_DIR)
for _p in (_PARENT_DIR,):
    if _p not in sys.path:
        sys.path.append(_p)

from blender_utils.mesh_utils import apply_all_transforms
from blender_utils.deformation_utils import apply_bone_field_delta
from blender_utils.armature_utils import apply_pose_as_rest
from blender_utils.weight_processing_utils import remove_propagated_weights


class PoseFinalizationStage:
    """ポーズ適用・ボーン調整・変換適用・ウェイトクリーンアップを担当するステージ
    
    責務:
        - ポーズをレストポーズとして適用（2回）
        - ボーンフィールドデルタ適用
        - すべての変換を適用
        - 伝播ウェイト削除
        - 元のボーンデータ復元
    
    ベースメッシュ依存:
        - 不要（衣装アーマチュアとfield_dataのみ使用）
    
    前提:
        - WeightTransferPostProcessStage が完了していること
    
    成果物:
        - レストポーズが適用された衣装アーマチュア
        - クリーンアップされたウェイト
    """
    
    # ベースメッシュ依存フラグ: 不要
    REQUIRES_BASE_MESH = False

    def __init__(self, pipeline):
        self.pipeline = pipeline

    def run(self):
        p = self.pipeline
        time = p.time_module

        # ポーズをレストポーズとして適用（1回目）
        print("Status: ポーズ適用中")
        apply_pose_as_rest(p.clothing_armature)
        # ボーンフィールドデルタ適用
        apply_bone_field_delta(
            p.clothing_armature,
            p.config_pair['field_data'],
            p.clothing_avatar_data,
        )
        # ポーズをレストポーズとして適用（2回目）
        print("Status: ポーズ適用中")
        apply_pose_as_rest(p.clothing_armature)
        # すべての変換を適用
        print("Status: すべての変換を適用中")
        apply_all_transforms()
        # 伝播ウェイト削除
        for obj in p.clothing_meshes:
            if obj.name in p.propagated_groups_map:
                remove_propagated_weights(obj, p.propagated_groups_map[obj.name])
        # 元のボーンデータ復元
        if p.original_humanoid_bones is not None or p.original_auxiliary_bones is not None:
            print("元のhumanoidBonesとauxiliaryBonesを復元中...")
            if p.original_humanoid_bones is not None:
                p.base_avatar_data['humanoidBones'] = p.original_humanoid_bones
            if p.original_auxiliary_bones is not None:
                p.base_avatar_data['auxiliaryBones'] = p.original_auxiliary_bones
        p.propagated_end_time = time.time()
