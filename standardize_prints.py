"""
print文の統一化スクリプト

統一方針:
- Error: / エラー: → [Error]
- Warning: / 警告: → [Warning]
- Status: / Progress: → そのまま維持（UIパース用）
- デバッグ的なprint → 削除
- セパレーター/トレースバック → そのまま維持
"""

import re
import os
from pathlib import Path

EXTRACTED_DIR = Path(r"c:\Users\tallcat\Documents\OpenFitter-Core\extracted")

# 維持するパターン（変更不要）
KEEP_PATTERNS = [
    r'print\(f?"Status:',        # ステータス（UI用）
    r'print\(f?"Progress:',      # 進捗（UI用）
    r'print\(traceback',         # トレースバック
    r"print\(['\"]={",           # セパレーター
    r'print\(f"\\n\{\'=\'',      # セパレーター
    r'print\(f"\{\'=\'',         # セパレーター
]

# 変換パターン: (正規表現, 置換関数)
TRANSFORMATIONS = [
    # Error: → [Error]
    (r'print\(f"Error: (.+?)"\)', lambda m: f'print(f"[Error] {m.group(1)}")'),
    (r'print\("Error: (.+?)"\)', lambda m: f'print("[Error] {m.group(1)}")'),
    # エラー: → [Error]
    (r'print\(f"エラー: (.+?)"\)', lambda m: f'print(f"[Error] {m.group(1)}")'),
    (r'print\("エラー: (.+?)"\)', lambda m: f'print("[Error] {m.group(1)}")'),
    # Warning: → [Warning]
    (r'print\(f"Warning: (.+?)"\)', lambda m: f'print(f"[Warning] {m.group(1)}")'),
    (r'print\("Warning: (.+?)"\)', lambda m: f'print("[Warning] {m.group(1)}")'),
    # 警告: → [Warning]
    (r'print\(f"警告: (.+?)"\)', lambda m: f'print(f"[Warning] {m.group(1)}")'),
    (r'print\("警告: (.+?)"\)', lambda m: f'print("[Warning] {m.group(1)}")'),
]

# 削除対象パターン（デバッグ情報）
DELETE_PATTERNS = [
    r'^\s*print\(\s*f"temp_shape_key_name:',
    r'^\s*print\(\s*f"temp_blend_shape_key_name:',
    r'^\s*print\(\s*f"source_blend_shape_name:',
    r'^\s*print\(\s*f"Processing config blend shape field:',
    r'^\s*print\(\s*f"Skipping base avatar blend shape field',
    r'^\s*print\(\s*f"Skipping creation of shape key',
    r'^\s*print\(\s*f"Skipping {label} -',
    r'^\s*print\(\s*f"Added deferred transition:',
    r'^\s*print\(\s*f"Removed shape key:',
    r'^\s*print\(\s*f"Applying mask weights to generated shape keys:',
    r'^\s*print\(\s*f"Applied mask weights to shape key:',
    r'^\s*print\(\s*f"config_pair\.get',
    r'^\s*print\(\s*f"Found \{sum',  # Found X objects
    r'^\s*print\(\s*f"{obj\.name} contains',
    r'^\s*print\(\s*f"chosen_parent:',
    r'^\s*print\(\s*"find_containing_objects:',
    r'^\s*print\(\s*f"Component with',
    r'^\s*print\(\s*f"Shape key:.*found on',
    r'^\s*print\(\s*f"Subdividing \{len',
    r'^\s*print\(\s*f"Adding optional humanoid bone group:',
    r'^\s*print\(\s*f"Creating missing Humanoid bone group',
    r'^\s*print\(\s*f"Restoring original weights for',
    r'^\s*print\(\s*f"Creating custom attributes for overlapping',
    r'^\s*print\(\s*f"Processed \{len\(vertex_max_distances',
    r'^\s*print\(\s*f"Restoring vertex weights using custom attribute',
    r'^\s*print\(\s*f"Successfully restored weights for',
    r'^\s*print\(\s*f"Removing \{sep_obj\.name',
]


def should_keep(line):
    """維持すべきprint文かどうか"""
    for pattern in KEEP_PATTERNS:
        if re.search(pattern, line):
            return True
    return False


def should_delete(line):
    """削除すべきprint文かどうか"""
    for pattern in DELETE_PATTERNS:
        if re.search(pattern, line.strip()):
            return True
    return False


def transform_line(line):
    """行を変換"""
    for pattern, replacement in TRANSFORMATIONS:
        match = re.search(pattern, line)
        if match:
            new_content = replacement(match)
            return re.sub(pattern, new_content.replace('\\', '\\\\'), line, count=1)
    return line


def process_file(file_path):
    """ファイルを処理"""
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    modified = False
    new_lines = []
    deletions = []
    transformations = []
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # print文を含む行かどうかチェック
        if 'print(' in line:
            # 複数行にまたがるprint文を処理
            full_line = line
            start_i = i
            
            # 開きカッコと閉じカッコのバランスをチェック
            open_count = full_line.count('(') - full_line.count(')')
            while open_count > 0 and i + 1 < len(lines):
                i += 1
                full_line += lines[i]
                open_count = full_line.count('(') - full_line.count(')')
            
            # 維持すべきパターン
            if should_keep(full_line):
                for j in range(start_i, i + 1):
                    new_lines.append(lines[j])
            # 削除すべきパターン
            elif should_delete(full_line):
                deletions.append((start_i + 1, full_line.strip()[:80]))
                modified = True
                # 削除後に空ブロックにならないようにpassを入れる必要があるかチェック
                if start_i > 0:
                    prev_line = lines[start_i - 1].rstrip()
                    if prev_line.endswith(':') and (i + 1 >= len(lines) or not lines[i + 1].strip() or lines[i + 1].strip().startswith('#')):
                        indent = len(line) - len(line.lstrip())
                        new_lines.append(' ' * indent + 'pass\n')
            else:
                # 変換を試みる
                transformed = transform_line(full_line)
                if transformed != full_line:
                    transformations.append((start_i + 1, full_line.strip()[:60], transformed.strip()[:60]))
                    modified = True
                    new_lines.append(transformed)
                else:
                    for j in range(start_i, i + 1):
                        new_lines.append(lines[j])
        else:
            new_lines.append(line)
        
        i += 1
    
    return new_lines, modified, deletions, transformations


def main():
    files_modified = 0
    total_deletions = 0
    total_transformations = 0
    
    for file_path in EXTRACTED_DIR.rglob("*.py"):
        if "__pycache__" in str(file_path):
            continue
            
        try:
            new_lines, modified, deletions, transformations = process_file(file_path)
            
            if modified:
                files_modified += 1
                rel_path = file_path.relative_to(EXTRACTED_DIR)
                
                if deletions:
                    print(f"\n[削除] {rel_path}:")
                    for line_num, content in deletions:
                        print(f"  L{line_num}: {content}...")
                        total_deletions += 1
                
                if transformations:
                    print(f"\n[変換] {rel_path}:")
                    for line_num, old, new in transformations:
                        print(f"  L{line_num}: {old}")
                        print(f"      → {new}")
                        total_transformations += 1
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.writelines(new_lines)
                    
        except Exception as e:
            print(f"Error processing {file_path}: {e}")
    
    print(f"\n{'='*60}")
    print(f"処理完了:")
    print(f"  - 変更ファイル数: {files_modified}")
    print(f"  - 削除したprint文: {total_deletions}")
    print(f"  - 変換したprint文: {total_transformations}")


if __name__ == "__main__":
    main()
