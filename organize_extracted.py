import os
import shutil
import re
from collections import defaultdict
import generate_stratification_report as analyzer

# カテゴリ定義 (標準ライブラリとの衝突を避けるため _utils を付与)
CATEGORIES = {
    'math': 'math_utils',
    'io': 'io_utils',
    'algo': 'algo_utils',
    'blender_utils': 'blender_utils',
    'utils': 'common_utils',
    'misc': 'misc_utils'
}

def classify_file(filename):
    name = filename.lower()
    
    # 1. Math / Geometry
    if any(x in name for x in ['calc', 'matrix', 'vec', 'transform', 'obb', 'triangle', 'normal', 'dist', 'barycentric', 'coords', 'intersect']):
        if 'apply_similarity_transform' in name: return 'math'
        if 'apply' in name and 'transform' in name: return 'blender_utils'
        return 'math'

    # 2. IO / Data
    if any(x in name for x in ['load', 'save', 'import', 'export', 'read', 'write', 'store', 'restore']):
        return 'io'

    # 3. Algorithms
    if any(x in name for x in ['find', 'search', 'cluster', 'sort', 'group', 'check', 'neighbor']):
        return 'algo'

    # 4. Blender Utils
    if any(x in name for x in ['modifier', 'shapekey', 'blendshape', 'weight', 'vertex', 'bone', 'armature', 'mesh', 'object', 'apply', 'reset', 'clear', 'create', 'merge', 'split', 'join', 'subdivide', 'propagate', 'adjust', 'process']):
        return 'blender_utils'

    # 5. String / Misc Utils
    if any(x in name for x in ['strip', 'name', 'rename', 'label', 'util', 'common']):
        return 'utils'

    return 'misc'

def update_imports(file_path, module_mapping):
    """
    ファイル内のimport文を更新する
    module_mapping: { old_module_name: new_category_name }
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    lines = content.split('\n')
    new_lines = []
    modified = False
    
    for line in lines:
        # from X import Y -> from category.X import Y
        match_from = re.match(r'^(\s*)from\s+(\w+)\s+import\s+(.+)$', line)
        # import X -> import category.X as X (or just import category.X)
        # 単純な import X はあまり使われていないと仮定し、from X import ... を主に対象にする
        # もし import X がある場合、コード内の X.func() も書き換える必要があり複雑になるため。
        
        if match_from:
            indent, module, imports = match_from.groups()
            if module in module_mapping:
                category = module_mapping[module]
                # 相対インポートではなく、sys.pathに追加されている前提で絶対インポートにする
                # ただし、extractedフォルダ自体がパスに入っている場合、category.module でアクセス可能
                new_line = f"{indent}from {category}.{module} import {imports}"
                new_lines.append(new_line)
                modified = True
                continue
        
        new_lines.append(line)
    
    if modified:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(new_lines))
        return True
    return False

def main():
    target_dir = os.path.join(os.getcwd(), "extracted")
    if not os.path.exists(target_dir):
        print("Target directory 'extracted' not found.")
        return

    # 1. 解析と分類
    print("Analyzing files...")
    files = [f for f in os.listdir(target_dir) if f.endswith('.py')]
    module_map = {f[:-3]: f for f in files}
    
    # 依存グラフ構築 (analyzer利用)
    graph = defaultdict(set)
    symbol_to_module = {m: m for m in module_map}
    
    for module_name, filename in module_map.items():
        path = os.path.join(target_dir, filename)
        defs = analyzer.get_definitions_and_lines(path)
        for d in defs:
            symbol_to_module[d] = module_name

    for module_name, filename in module_map.items():
        path = os.path.join(target_dir, filename)
        calls = analyzer.get_calls(path)
        for call in calls:
            if call in symbol_to_module:
                target_mod = symbol_to_module[call]
                if target_mod != module_name:
                    graph[module_name].add(target_mod)

    levels = analyzer.calculate_levels(graph, list(module_map.keys()))

    # 移動計画作成
    moves = {} # module_name -> new_category
    
    for module, level in levels.items():
        if level <= 1: # Level 0, 1のみ移動
            filename = module_map.get(module)
            if not filename: continue
            
            cat_key = classify_file(filename)
            moves[module] = CATEGORIES[cat_key]

    # 2. ディレクトリ作成
    for cat in set(moves.values()):
        cat_path = os.path.join(target_dir, cat)
        os.makedirs(cat_path, exist_ok=True)
        # __init__.py 作成
        init_path = os.path.join(cat_path, '__init__.py')
        if not os.path.exists(init_path):
            with open(init_path, 'w') as f:
                f.write("")

    # 3. ファイル移動
    print("Moving files...")
    for module, category in moves.items():
        filename = module_map[module]
        src = os.path.join(target_dir, filename)
        dst = os.path.join(target_dir, category, filename)
        
        if os.path.exists(src):
            shutil.move(src, dst)
            print(f"Moved {filename} -> {category}/")
        else:
            print(f"Warning: File {filename} not found (maybe already moved?)")

    # 4. インポートの更新
    print("Updating imports...")
    # extracted以下の全ファイルを再スキャン（サブディレクトリ含む）
    all_files = []
    for root, dirs, files in os.walk(target_dir):
        for file in files:
            if file.endswith('.py'):
                all_files.append(os.path.join(root, file))
    
    count = 0
    for file_path in all_files:
        if update_imports(file_path, moves):
            print(f"Updated imports in {os.path.basename(file_path)}")
            count += 1
            
    print(f"Done. Updated {count} files.")

if __name__ == "__main__":
    main()
