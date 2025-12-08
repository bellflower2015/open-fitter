import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import bpy
from processing_context import ProcessingContext
from stages.asset_loading import AssetLoadingStage
from stages.asset_normalization import AssetNormalizationStage
from stages.blendshape_application import BlendShapeApplicationStage
from stages.bone_replacement import BoneReplacementStage
from stages.export_preparation import ExportPreparationStage
from stages.mesh_deformation import MeshDeformationStage
from stages.pose_application import PoseApplicationStage
from stages.pose_finalization import PoseFinalizationStage
from stages.template_adjustment import TemplateAdjustmentStage
from stages.weight_transfer_execution import WeightTransferExecutionStage
from stages.weight_transfer_postprocess import WeightTransferPostProcessStage
from stages.weight_transfer_preparation import WeightTransferPreparationStage


class OutfitRetargetPipeline:
    """衣装リターゲティングパイプライン (OutfitRetargetingSystem のコア処理)
    
    ベースアバターから衣装メッシュへウェイト・形状・ポーズを転送し、
    最終的なFBXファイルを出力する。
    
    Stages:
        1. AssetLoading: ファイル読み込み・FBXインポート
        2. AssetNormalization: アセット正規化・初期設定
        3. TemplateAdjustment: Template固有補正（条件付き）
        4. BlendShapeApplication: BlendShape変形フィールド適用
        5. PoseApplication: ポーズ適用・頂点属性設定
        6. MeshDeformation: メッシュ変形処理（サイクル1）
        7. WeightTransferPreparation: ウェイト転送準備
        8. WeightTransferExecution: ウェイト転送本体
        9. WeightTransferPostProcess: ウェイト転送後処理
        10. PoseFinalization: ポーズ適用・変形の伝搬
        11. BoneReplacement: ヒューマノイドボーン置換
        12. ExportPreparation: エクスポート準備・FBX出力
    """
    
    # ProcessingContextに委譲する属性のリスト
    _CTX_ATTRS = frozenset({
        'base_mesh', 'base_armature', 'base_avatar_data',
        'clothing_meshes', 'clothing_armature', 'clothing_avatar_data',
        'cloth_metadata', 'vertex_index_mapping',
        'use_subdivision', 'use_triangulation', 'propagated_groups_map',
        'original_humanoid_bones', 'original_auxiliary_bones',
        'is_A_pose', 'blend_shape_labels',
        'base_weights_time', 'blendshape_time', 'pose_time',
        'cycle1_end_time', 'cycle2_post_end',
        'propagated_end_time', 'bones_replace_time',
        'containing_objects', 'armature_settings_dict',
        'time_module', 'start_time'
    })

    def __init__(self, args, config_pair, pair_index, total_pairs, overall_start_time):
        object.__setattr__(self, 'args', args)
        object.__setattr__(self, 'config_pair', config_pair)
        object.__setattr__(self, 'pair_index', pair_index)
        object.__setattr__(self, 'total_pairs', total_pairs)
        object.__setattr__(self, 'overall_start_time', overall_start_time)
        object.__setattr__(self, 'ctx', ProcessingContext())

    def __getattr__(self, name):
        if name in OutfitRetargetPipeline._CTX_ATTRS:
            return getattr(self.ctx, name)
        raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")

    def __setattr__(self, name, value):
        if name in OutfitRetargetPipeline._CTX_ATTRS:
            setattr(self.ctx, name, value)
        else:
            object.__setattr__(self, name, value)

    def execute(self):
        try:
            import time

            self.time_module = time
            self.start_time = time.time()

            self.use_subdivision = not self.args.no_subdivision
            if self.pair_index != 0:
                self.use_subdivision = False

            self.use_triangulation = not self.args.no_triangle

            bpy.ops.object.mode_set(mode='OBJECT')

            is_final_pair = (self.pair_index == self.total_pairs - 1)
            pair_info = f"[{self.pair_index + 1}/{self.total_pairs}]"

            # ファイル読み込み・FBXインポート
            print(f"Status: {pair_info} アセット読み込み中...")
            AssetLoadingStage(self).run()
            # アセット正規化・初期設定
            print(f"Status: {pair_info} アセット正規化中...")
            AssetNormalizationStage(self).run()
            # Template専用の調整処理
            if not TemplateAdjustmentStage(self).run():
                return None
            # BlendShape変形フィールド適用
            print(f"Status: {pair_info} BlendShape変形フィールド適用中...")
            BlendShapeApplicationStage(self).run()
            # ポーズ適用・頂点属性設定
            print(f"Status: {pair_info} ポーズ適用中...")
            PoseApplicationStage(self).run()
            # サイクル1: メッシュ変形処理
            print(f"Status: {pair_info} メッシュ変形処理中...")
            MeshDeformationStage(self).run()

            # サイクル2: ウェイト転送準備
            print(f"Status: {pair_info} ウェイト転送準備中...")
            WeightTransferPreparationStage(self).run()
            
            # サイクル2: ウェイト転送本体（最終pairでのみ実行）
            if is_final_pair:
                print(f"Status: {pair_info} ウェイト転送実行中...")
                WeightTransferExecutionStage(self).run()
            
            # サイクル2: ウェイト転送後処理（アーマチュア設定復元は常に必要）
            print(f"Status: {pair_info} ウェイト転送後処理中...")
            WeightTransferPostProcessStage(self).run()

            # ポーズ適用・変形の伝搬
            print(f"Status: {pair_info} ポーズ確定処理中...")
            PoseFinalizationStage(self).run()
            # ヒューマノイドボーン置換
            print(f"Status: {pair_info} ボーン置換中...")
            BoneReplacementStage(self).run()
            # エクスポート準備・FBX出力
            print(f"Status: {pair_info} エクスポート処理中...")
            ExportPreparationStage(self).run()

            total_time = time.time() - self.start_time
            return True

        except Exception as e:
            import traceback

            print("============= Error Details =============")
            print("\n============= Full Stack Trace =============")
            print(traceback.format_exc())
            print("==========================================")

            output_blend = self.args.output.rsplit('.', 1)[0] + '.blend'
            bpy.ops.wm.save_as_mainfile(filepath=output_blend)

            return False


# 後方互換性のためのエイリアス
SingleConfigProcessor = OutfitRetargetPipeline
ClothingRetargetPipeline = OutfitRetargetPipeline


def process_single_config(args, config_pair, pair_index, total_pairs, overall_start_time):
    """後方互換性のためのラッパー関数。OutfitRetargetPipelineを直接使用することを推奨。"""
    pipeline = OutfitRetargetPipeline(args, config_pair, pair_index, total_pairs, overall_start_time)
    return pipeline.execute()