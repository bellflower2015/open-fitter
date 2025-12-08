"""BoneReplacementStage: ヒューマノイドボーン置換を担当するステージ"""

import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

_CURR_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT_DIR = os.path.dirname(_CURR_DIR)
for _p in (_PARENT_DIR,):
    if _p not in sys.path:
        sys.path.append(_p)

from replace_humanoid_bones import replace_humanoid_bones


class BoneReplacementStage:
    """ヒューマノイドボーン置換を担当するステージ
    
    責務:
        - ベースアーマチュアから衣装アーマチュアへのヒューマノイドボーン置換
    
    ベースメッシュ依存:
        - 必須（base_armatureからボーンをコピー）
        - 最終pairでのみ実行される
    
    前提:
        - PoseFinalizationStage が完了していること
    
    成果物:
        - ヒューマノイドボーンが置換された衣装アーマチュア
    """
    
    # ベースメッシュ依存フラグ: 必須（base_armature必要）
    REQUIRES_BASE_MESH = True

    def __init__(self, pipeline):
        self.pipeline = pipeline

    def run(self):
        p = self.pipeline
        time = p.time_module
        is_final_pair = (p.pair_index == p.total_pairs - 1)

        # 中間pairではボーン置換をスキップ（base_armatureがNone）
        if not is_final_pair:
            return

        # ベースポーズファイルパスの取得
        base_pose_filepath = None
        if p.config_pair.get('do_not_use_base_pose', 0) == 0:
            base_pose_filepath = p.base_avatar_data.get('basePose', None)
            if base_pose_filepath:
                pose_dir = os.path.dirname(
                    os.path.abspath(p.config_pair['base_avatar_data'])
                )
                base_pose_filepath = os.path.join(pose_dir, base_pose_filepath)

        # ヒューマノイドボーン置換（最終pairのみ）
        if p.pair_index == 0:
            replace_humanoid_bones(
                p.base_armature,
                p.clothing_armature,
                p.base_avatar_data,
                p.clothing_avatar_data,
                True,
                base_pose_filepath,
                p.clothing_meshes,
                False,
            )
        else:
            replace_humanoid_bones(
                p.base_armature,
                p.clothing_armature,
                p.base_avatar_data,
                p.clothing_avatar_data,
                False,
                base_pose_filepath,
                p.clothing_meshes,
                True,
            )

        p.bones_replace_time = time.time()
