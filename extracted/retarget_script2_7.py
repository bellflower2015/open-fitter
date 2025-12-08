import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import argparse

import bpy
from parse_args import parse_args

# V1（forループ版 + is_final_pair最適化）を使用
# V2は設計見直しが必要なため一時的に無効化
from process_single_config import OutfitRetargetPipeline


def main_v1(args, config_pairs, start_time):
    """V1アーキテクチャ: forループでconfig_pairsを順次処理
    
    is_final_pair最適化により、中間pairではTemplate.fbxをロードしない。
    """
    import time
    
    print(f"Status: パイプライン開始 ({len(config_pairs)} pair)")

    success = True
    for i, config_pair in enumerate(config_pairs):
        pipeline = OutfitRetargetPipeline(
            args, config_pair, i, len(config_pairs), start_time
        )
        result = pipeline.execute()
        if not result:
            success = False
            break
    
    return success


def main():
    """メインエントリポイント
    
    V1（forループ + is_final_pair最適化）を使用。
    中間pairではTemplate.fbxをロードせず、最終pairでのみベースアバターをロード。
    """
    try:
        import time
        start_time = time.time()

        sys.stdout.reconfigure(line_buffering=True)
        
        print(f"Status: 初期化中...")
        bpy.ops.preferences.addon_enable(module='robust-weight-transfer')
        # Parse command line arguments
        args, config_pairs = parse_args()
        # V1パイプラインを実行
        success = main_v1(args, config_pairs, start_time)
        
        total_time = time.time() - start_time
        print(f"Status: 完了 ({total_time:.1f}秒)")
        print(f"Progress: 1.00")
        
        return success
        
    except Exception as e:
        import traceback
        print("============= Fatal Error =============")
        print("\n============= Full Stack Trace =============")
        print(traceback.format_exc())
        print("=====================================")
        return False

if __name__ == "__main__":
    main()
