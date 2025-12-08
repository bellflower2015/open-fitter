"""
空のブロック（if/else/for/except/try後にボディがない）を修正するスクリプト
passを挿入するか、不要なブロックを削除する
"""
import re
import os
from pathlib import Path

def fix_empty_blocks(filepath: str) -> tuple[bool, list[str]]:
    """空のブロックを修正する"""
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    changes = []
    i = 0
    new_lines = []
    
    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip()
        
        # if/elif/else/for/while/try/except/finally/with/def/class で終わる行を検出
        block_pattern = r'^(\s*)(if\s+.+:|elif\s+.+:|else:|for\s+.+:|while\s+.+:|try:|except.*:|finally:|with\s+.+:|def\s+.+:|class\s+.+:)\s*$'
        match = re.match(block_pattern, stripped)
        
        if match:
            indent = match.group(1)
            block_type = match.group(2)
            expected_indent = indent + '    '  # 次の行は1レベル深いインデントが必要
            
            # 次の行をチェック
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                next_stripped = next_line.rstrip()
                
                # 次の行が空行またはコメントのみの場合、さらに先を見る
                j = i + 1
                while j < len(lines):
                    check_line = lines[j].rstrip()
                    if check_line == '' or (check_line.strip().startswith('#') and not check_line.startswith(expected_indent)):
                        j += 1
                        continue
                    break
                
                if j < len(lines):
                    actual_next = lines[j]
                    actual_next_stripped = actual_next.rstrip()
                    
                    # 次の実際のコードが同じかより浅いインデントなら、ブロックが空
                    if actual_next_stripped and not actual_next_stripped.startswith(expected_indent):
                        # else: や except: で空なら削除、それ以外ならpassを挿入
                        if block_type.strip() in ['else:', 'finally:'] or block_type.strip().startswith('except'):
                            # 空のelse/except/finallyは削除
                            changes.append(f"Line {i+1}: Removed empty '{block_type.strip()}'")
                            i += 1
                            continue
                        elif block_type.strip().startswith('if ') and not any(
                            re.match(r'^\s*(elif|else)', lines[k]) for k in range(j, min(j+5, len(lines)))
                        ):
                            # 単独のif文で空なら削除
                            changes.append(f"Line {i+1}: Removed empty '{block_type.strip()[:30]}...'")
                            i += 1
                            continue
                        else:
                            # passを挿入
                            new_lines.append(line)
                            new_lines.append(expected_indent + 'pass\n')
                            changes.append(f"Line {i+1}: Added 'pass' after '{block_type.strip()[:30]}...'")
                            i += 1
                            continue
        
        new_lines.append(line)
        i += 1
    
    if changes:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        return True, changes
    return False, []

def main():
    extracted_dir = Path(r'c:\Users\tallcat\Documents\OpenFitter-Core\extracted')
    
    error_files = [
        'apply_distance_normal_based_smoothing.py',
        'apply_field_delta_with_rigid_transform.py',
        'blender_utils/blendshape_operation.py',
        'set_humanoid_bone_inherit_scale.py',
        'algo_utils/component_utils.py',
        'algo_utils/mesh_topology_utils.py',
        'blender_utils/vertex_group_utils.py',
        'blender_utils/deformation_utils.py',
        'blender_utils/mesh_utils.py',
        'blender_utils/process_clothing_avatar.py',
        'blender_utils/subdivision_utils.py',
        'io_utils/io_utils.py',
        'math_utils/apply_distance_falloff_blend.py',
        'stages/asset_normalization.py',
        'stages/compare_side_and_bone_weights.py',
        'stages/restore_head_weights.py',
        'stages/weight_transfer_preparation.py',
        'symmetric_field_deformer/blendshape_processor.py',
    ]
    
    total_changes = 0
    for rel_path in error_files:
        filepath = extracted_dir / rel_path
        if filepath.exists():
            modified, changes = fix_empty_blocks(str(filepath))
            if modified:
                print(f"\n{rel_path}:")
                for change in changes:
                    print(f"  {change}")
                total_changes += len(changes)
    
    print(f"\n\nTotal changes: {total_changes}")

if __name__ == '__main__':
    main()
