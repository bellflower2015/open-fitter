"""WeightTransferExecutionStage: ウェイト転送本体を担当するステージ"""

import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

_CURR_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT_DIR = os.path.dirname(_CURR_DIR)
for _p in (_PARENT_DIR,):
    if _p not in sys.path:
        sys.path.append(_p)

from math_utils.weight_utils import (
    normalize_overlapping_vertices_weights,
)
from process_weight_transfer_with_component_normalization import (
    process_weight_transfer_with_component_normalization,
)
from temporarily_merge_for_weight_transfer import temporarily_merge_for_weight_transfer


class WeightTransferExecutionStage:
    """ウェイト転送本体を担当するステージ
    
    責務:
        - 包含関係がある場合: 一時マージしてウェイト転送
        - 個別メッシュ: 連結成分正規化付きウェイト転送
        - 重複頂点のウェイト正規化
    
    ベースメッシュ依存:
        - 必須（base_meshからウェイトを転送）
        - 最終pairでのみ実行される
    
    前提:
        - WeightTransferPreparationStage が完了していること
        - containing_objects が設定されていること
    
    成果物:
        - ウェイトが転送された衣装メッシュ
    """
    
    # ベースメッシュ依存フラグ: 必須
    REQUIRES_BASE_MESH = True

    def __init__(self, pipeline):
        self.pipeline = pipeline

    def run(self):
        p = self.pipeline
        time = p.time_module

        print("Status: サイクル2ウェイト転送中")
        print(f"Progress: {(p.pair_index + 0.6) / p.total_pairs * 0.9:.3f}")

        weight_transfer_start = time.time()
        weight_transfer_processed = set()

        # 包含関係があるメッシュのウェイト転送
        for obj in p.clothing_meshes:
            if obj in weight_transfer_processed:
                continue

            obj_start = time.time()
            if obj in p.containing_objects and p.containing_objects[obj]:
                contained_objects = p.containing_objects[obj]
                print(
                    f"{obj.name} contains {contained_objects} other objects within distance 0.02 - applying joint weight transfer"
                )

                temporarily_merge_for_weight_transfer(
                    obj,
                    contained_objects,
                    p.base_armature,
                    p.base_avatar_data,
                    p.clothing_avatar_data,
                    p.config_pair['field_data'],
                    p.clothing_armature,
                    p.config_pair.get('next_blendshape_settings', []),
                    p.cloth_metadata,
                )

                weight_transfer_processed.add(obj)
                weight_transfer_processed.update(contained_objects)

            print(f"  {obj.name}の包含ウェイト転送: {time.time() - obj_start:.2f}秒")

        # 個別メッシュのウェイト転送
        for obj in p.clothing_meshes:
            if obj in weight_transfer_processed:
                continue

            obj_start = time.time()
            print(f"Applying individual weight transfer to {obj.name}")

            process_weight_transfer_with_component_normalization(
                obj,
                p.base_armature,
                p.base_avatar_data,
                p.clothing_avatar_data,
                p.config_pair['field_data'],
                p.clothing_armature,
                p.config_pair.get('next_blendshape_settings', []),
                p.cloth_metadata,
            )

            weight_transfer_processed.add(obj)
            print(f"  {obj.name}の個別ウェイト転送: {time.time() - obj_start:.2f}秒")

        # 重複頂点のウェイト正規化
        normalize_overlapping_vertices_weights(p.clothing_meshes, p.base_avatar_data)

        weight_transfer_end = time.time()
        print(f"ウェイト転送処理全体: {weight_transfer_end - weight_transfer_start:.2f}秒")
