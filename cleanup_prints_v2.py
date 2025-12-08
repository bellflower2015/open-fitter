"""
Print/Time クリーンアップ - 実行版

段階的に削除:
1. 時間測定print（秒で終わる、time差分を含む）
2. デバッグ用print（変数値の出力）
3. 細かいtime.time()代入

保持:
- Status: / Progress: （進捗表示）
- Error / Warning （エラー報告）
- 処理完了 メッセージ
- ステージ開始/終了マーカー
"""

import re
import os
from pathlib import Path
from typing import List, Tuple, Set


def should_keep_line(line: str) -> bool:
    """この行を保持すべきかどうか"""
    stripped = line.strip()
    
    # print文でない場合は保持
    if not stripped.startswith('print('):
        return True
    
    # 保持パターン
    keep_patterns = [
        r'Status:',           # 進捗ステータス
        r'Progress:',         # 進捗バー
        r'Error',             # エラー
        r'Warning',           # 警告
        r'Exception',         # 例外
        r'処理完了',           # 完了メッセージ
        r'=== Stage',         # ステージマーカー
        r'^\s*print\(\)$',    # 空行print
    ]
    
    for pattern in keep_patterns:
        if re.search(pattern, line, re.IGNORECASE):
            return True
    
    return False


def should_remove_print(line: str) -> Tuple[bool, str]:
    """このprint文を削除すべきかどうか"""
    stripped = line.strip()
    
    if not stripped.startswith('print('):
        return False, ''
    
    # 削除パターン（優先度順）
    remove_patterns = [
        (r':\s*\d+\.\d+秒', 'time_seconds'),           # 1.23秒
        (r':\s*\{[^}]*\}秒', 'time_fstring'),          # {var}秒
        (r':\s*\{[^}]*-[^}]*\}', 'time_diff'),        # {end - start}
        (r'\.2f\}秒', 'time_format'),                  # :.2f}秒
        (r'config_pair', 'config_debug'),             # config_pair
        (r'Found \d+', 'found_count'),                # Found N
        (r'^\s*print\(f"[^"]*:\s*\{[^}]+\}"', 'var_debug'),  # f"xxx: {var}"
        (r'Processing mesh', 'processing_mesh'),
        (r'Applying', 'applying'),
        (r'Loading', 'loading'),
        (r'インポート', 'import_jp'),
        (r'複製', 'duplicate_jp'),
        (r'検出', 'detect_jp'),
        (r'頂点', 'vertex_jp'),
        (r'ウェイト', 'weight_jp'),
        (r'ボーン', 'bone_jp'),
        (r'メッシュ', 'mesh_jp'),
        (r'アーマチュア', 'armature_jp'),
    ]
    
    for pattern, reason in remove_patterns:
        if re.search(pattern, line):
            return True, reason
    
    return False, ''


def should_remove_time_assignment(line: str) -> Tuple[bool, str]:
    """time.time()代入を削除すべきかどうか"""
    stripped = line.strip()
    
    # 保持すべきtime変数
    keep_vars = ['start_time', 'overall_start_time', 'time_module']
    for var in keep_vars:
        if var in line and '=' in line:
            return False, ''
    
    # time.time() または p.time_module.time() の代入
    if re.search(r'=\s*(time\.time\(\)|p\.time_module\.time\(\))', line):
        return True, 'time_assignment'
    
    return False, ''


def process_file(filepath: Path, dry_run: bool = True) -> dict:
    """ファイルを処理"""
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    result = {
        'removed_prints': 0,
        'removed_time': 0,
        'kept': 0,
        'changes': []
    }
    
    new_lines = []
    skip_next_empty = False
    
    for i, line in enumerate(lines, 1):
        # 空行は前の削除に続く場合スキップ
        if skip_next_empty and line.strip() == '':
            skip_next_empty = False
            continue
        skip_next_empty = False
        
        # print文チェック
        remove_print, reason = should_remove_print(line)
        if remove_print:
            result['removed_prints'] += 1
            result['changes'].append((i, 'print', reason, line.strip()[:60]))
            skip_next_empty = True
            continue
        
        # time代入チェック
        remove_time, reason = should_remove_time_assignment(line)
        if remove_time:
            result['removed_time'] += 1
            result['changes'].append((i, 'time', reason, line.strip()[:60]))
            skip_next_empty = True
            continue
        
        # 保持
        if line.strip().startswith('print('):
            result['kept'] += 1
        
        new_lines.append(line)
    
    if not dry_run and (result['removed_prints'] > 0 or result['removed_time'] > 0):
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
    
    return result


def process_directory(directory: Path, dry_run: bool = True, verbose: bool = False):
    """ディレクトリ内の全ファイルを処理"""
    total = {
        'files': 0,
        'removed_prints': 0,
        'removed_time': 0,
        'kept': 0
    }
    
    for pyfile in sorted(directory.rglob('*.py')):
        # スクリプト自体は除外
        if 'cleanup' in pyfile.name:
            continue
        
        result = process_file(pyfile, dry_run)
        
        if result['removed_prints'] > 0 or result['removed_time'] > 0:
            total['files'] += 1
            total['removed_prints'] += result['removed_prints']
            total['removed_time'] += result['removed_time']
            total['kept'] += result['kept']
            
            if verbose:
                print(f"\n{pyfile.relative_to(directory)}")
                print(f"  Removed: {result['removed_prints']} prints, {result['removed_time']} time")
                print(f"  Kept: {result['kept']} prints")
                if verbose and result['changes']:
                    for line_no, type_, reason, content in result['changes'][:5]:
                        print(f"    L{line_no} [{type_}:{reason}] {content}...")
                    if len(result['changes']) > 5:
                        print(f"    ... and {len(result['changes']) - 5} more")
    
    return total


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true', help='Apply changes')
    parser.add_argument('--verbose', '-v', action='store_true')
    parser.add_argument('--file', type=str, help='Single file')
    args = parser.parse_args()
    
    dry_run = not args.apply
    
    print("=" * 60)
    print("PRINT/TIME CLEANUP")
    print("=" * 60)
    print(f"Mode: {'DRY RUN' if dry_run else '*** APPLYING CHANGES ***'}")
    print()
    
    if args.file:
        result = process_file(Path(args.file), dry_run)
        print(f"Removed: {result['removed_prints']} prints, {result['removed_time']} time")
        print(f"Kept: {result['kept']} prints")
        if args.verbose:
            for line_no, type_, reason, content in result['changes']:
                print(f"  L{line_no} [{type_}:{reason}] {content}")
    else:
        directory = Path(__file__).parent / 'extracted'
        total = process_directory(directory, dry_run, args.verbose)
        
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"Files modified: {total['files']}")
        print(f"Prints removed: {total['removed_prints']}")
        print(f"Time assignments removed: {total['removed_time']}")
        print(f"Prints kept: {total['kept']}")
        
        if dry_run:
            print("\n*** Run with --apply to make changes ***")


if __name__ == '__main__':
    main()
