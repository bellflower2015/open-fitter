"""PoseApplicationStage: 衣装へのポーズ適用と頂点属性設定を担当するステージ"""

import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

_CURR_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT_DIR = os.path.dirname(_CURR_DIR)
for _p in (_PARENT_DIR,):
    if _p not in sys.path:
        sys.path.append(_p)

from add_clothing_pose_from_json import add_clothing_pose_from_json
from algo_utils.bone_group_utils import create_hinge_bone_group
from blender_utils.weight_transfer_utils import (
    create_overlapping_vertices_attributes,
)


class PoseApplicationStage:
    """衣装アーマチュアへのポーズ適用と頂点属性設定を担当するステージ
    
    責務:
        - 衣装アーマチュアへのポーズ適用
        - 重複頂点属性の設定
        - ヒンジボーングループの作成
    
    ベースメッシュ依存:
        - 不要（衣装データとpose_dataのみ使用）
        - base_avatar_dataは参照するがbase_meshは不要
    
    前提:
        - BlendShapeApplicationStage が完了していること
    
    成果物:
        - ポーズが適用された衣装アーマチュア
        - 重複頂点属性が設定された衣装メッシュ
    """
    
    # ベースメッシュ依存フラグ: 不要（base_avatar_dataのみ参照）
    REQUIRES_BASE_MESH = False

    def __init__(self, pipeline):
        self.pipeline = pipeline

    def run(self):
        p = self.pipeline
        time = p.time_module

        # ポーズ適用
        add_clothing_pose_from_json(
            p.clothing_armature,
            p.config_pair['pose_data'],
            p.config_pair['init_pose'],
            p.config_pair['clothing_avatar_data'],
            p.config_pair['base_avatar_data'],
        )

        # 重複頂点属性設定
        create_overlapping_vertices_attributes(p.clothing_meshes, p.base_avatar_data)

        # ヒンジボーングループ作成
        for obj in p.clothing_meshes:
            create_hinge_bone_group(obj, p.clothing_armature, p.clothing_avatar_data)

