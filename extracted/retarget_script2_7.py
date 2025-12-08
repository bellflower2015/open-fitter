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
    
    print(f"\n{'='*60}")
    print(f"OutfitRetargetPipeline V1 - is_final_pair最適化版")
    print(f"{'='*60}")
    print(f"{'='*60}")

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
        
        print(f"Status: アドオン有効化中")
        print(f"Progress: 0.01")
        bpy.ops.preferences.addon_enable(module='robust-weight-transfer')
        # Parse command line arguments
        print(f"Status: 引数解析中")
        print(f"Progress: 0.02")
        args, config_pairs = parse_args()
        # V1パイプラインを実行
        print("Using Pipeline V1 (is_final_pair最適化版)")
        success = main_v1(args, config_pairs, start_time)
        
        total_time = time.time() - start_time
        print(f"Progress: 1.00")
        print(f"\n{'='*60}")
        print(f"全体処理完了")
        print(f"{'='*60}")
        
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
