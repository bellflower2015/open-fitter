"""WeightTransferPostProcessStage: ウェイト転送後の後処理を担当するステージ"""

import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

_CURR_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT_DIR = os.path.dirname(_CURR_DIR)
for _p in (_PARENT_DIR,):
    if _p not in sys.path:
        sys.path.append(_p)

from blender_utils.armature_utils import (
    set_armature_modifier_target_armature,
    set_armature_modifier_visibility,
)


class WeightTransferPostProcessStage:
    """ウェイト転送後の後処理を担当するステージ
    
    責務:
        - アーマチュアモディファイアの可視性復元
        - アーマチュアターゲットの復元（衣装アーマチュアに戻す）
    
    ベースメッシュ依存:
        - 不要（衣装のアーマチュア設定復元のみ）
    
    前提:
        - WeightTransferExecutionStage が完了していること
    
    成果物:
        - cycle2_post_end タイムスタンプ
        - アーマチュア設定が復元された衣装メッシュ
    """
    
    # ベースメッシュ依存フラグ: 不要
    REQUIRES_BASE_MESH = False

    def __init__(self, pipeline):
        self.pipeline = pipeline

    def run(self):
        p = self.pipeline
        time = p.time_module

        print("Status: サイクル2後処理中")
        for obj in p.clothing_meshes:
            print("cycle2 (post-weight transfer) " + obj.name)

            # アーマチュアモディファイアの可視性を復元
            set_armature_modifier_visibility(obj, True, True)

            # アーマチュアターゲットを衣装アーマチュアに戻す
            set_armature_modifier_target_armature(obj, p.clothing_armature)

        p.cycle2_post_end = time.time()
