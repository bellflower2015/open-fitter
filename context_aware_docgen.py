import os
import ast
import json
import sys
from collections import defaultdict
import google.generativeai as genai

# ==========================================
# 1. 設定
# ==========================================

# ターゲットとする関数
TARGET_FUNCTION = "retarget_script2_7"

TARGET_DIR = os.path.join(os.getcwd(), "extracted")
MODEL_NAME = "gemini-3-pro-preview"  # 利用不可なら "gemini-1.5-pro" に変更してください
DOC_OUTPUT_DIR = os.path.join(os.getcwd(), "generated_documents")
ALIAS_INDEX_PATH = os.path.join(DOC_OUTPUT_DIR, "_aliases.json")

# os.environ["GOOGLE_API_KEY"] = "YOUR_API_KEY"
if not os.getenv("GOOGLE_API_KEY"):
    print("Error: GOOGLE_API_KEY environment variable not set.")
    exit(1)

genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))


def ensure_doc_dir():
    os.makedirs(DOC_OUTPUT_DIR, exist_ok=True)


def ensure_parent_dir(path):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def sanitize_func_name(func_name):
    """Convert function key to path parts. Example: a.b.foo -> ["a", "b", "foo"]."""
    parts = func_name.replace(os.sep, ".").split(".")
    if len(parts) >= 2 and parts[-1] == parts[-2]:
        parts.pop()
    return parts


def get_doc_path(func_name, analyzer=None):
    """Resolve doc path using analyzer's module map when available; fallback to name parsing."""
    if analyzer:
        resolved = analyzer.resolve_symbol(func_name)
        if resolved and resolved in analyzer.function_map:
            info = analyzer.function_map[resolved]
            # Use file directory relative to root, not module path
            rel_path = os.path.relpath(info["path"], analyzer.root_dir)
            rel_dir = os.path.dirname(rel_path)
            
            leaf = info.get("name") or func_name
            return os.path.join(DOC_OUTPUT_DIR, rel_dir, f"{leaf}.json")

    parts = sanitize_func_name(func_name)
    if not parts:
        return os.path.join(DOC_OUTPUT_DIR, "unknown.json")
    *dirs, leaf = parts
    return os.path.join(DOC_OUTPUT_DIR, *dirs, f"{leaf}.json")


def collapse_duplicate_module_func(func_name):
    """Collapse names like foo.foo to a single leaf for display."""
    parts = func_name.split(".")
    if len(parts) >= 2 and parts[-1] == parts[-2]:
        return parts[-1]
    return func_name


_ALIAS_INDEX_CACHE = None


def load_alias_index():
    """Load alias index mapping alias -> canonical function names."""
    global _ALIAS_INDEX_CACHE
    if _ALIAS_INDEX_CACHE is not None:
        return _ALIAS_INDEX_CACHE

    ensure_doc_dir()
    if os.path.exists(ALIAS_INDEX_PATH):
        try:
            with open(ALIAS_INDEX_PATH, 'r', encoding='utf-8') as f:
                _ALIAS_INDEX_CACHE = json.load(f)
        except Exception as exc:
            print(f"Warning: Failed to read alias index '{ALIAS_INDEX_PATH}': {exc}")
            _ALIAS_INDEX_CACHE = {}
    else:
        _ALIAS_INDEX_CACHE = {}
    return _ALIAS_INDEX_CACHE


def save_alias_index(index):
    """Persist alias index and refresh cache."""
    ensure_doc_dir()
    try:
        with open(ALIAS_INDEX_PATH, 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        print(f"Warning: Failed to save alias index '{ALIAS_INDEX_PATH}': {exc}")
        return

    global _ALIAS_INDEX_CACHE
    _ALIAS_INDEX_CACHE = index


def register_alias(alias_name, canonical_name, analyzer=None):
    """Register alias -> canonical mapping and remove stale alias files."""
    if not alias_name or not canonical_name or alias_name == canonical_name:
        return

    index = load_alias_index()
    if index.get(alias_name) != canonical_name:
        index[alias_name] = canonical_name
        save_alias_index(index)

    alias_path = get_doc_path(alias_name, analyzer=analyzer)
    canonical_path = get_doc_path(canonical_name, analyzer=analyzer)
    if os.path.exists(alias_path) and alias_path != canonical_path:
        try:
            os.remove(alias_path)
            print(f"  [Cache] Removed duplicate alias file: {alias_path}")
        except Exception as exc:
            print(f"Warning: Failed to remove alias file '{alias_path}': {exc}")


def load_existing_doc(*func_names, analyzer=None):
    alias_index = load_alias_index()
    for name in func_names:
        if not name:
            continue
        candidate_names = [name]
        canonical = alias_index.get(name)
        if canonical and canonical not in candidate_names:
            candidate_names.insert(0, canonical)

        for candidate in candidate_names:
            path = get_doc_path(candidate, analyzer=analyzer)
            if os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except Exception as exc:
                    print(f"Warning: Failed to read cached doc '{path}': {exc}")
    return None


def save_doc(func_name, doc, extra_keys=None, analyzer=None):
    if not doc:
        return
    path = get_doc_path(func_name, analyzer=analyzer)
    ensure_parent_dir(path)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        print(f"Warning: Failed to save doc '{path}': {exc}")

    if extra_keys:
        for alias in extra_keys:
            register_alias(alias, func_name, analyzer=analyzer)

# ==========================================
# 2. 解析 & コード抽出ユーティリティ
# ==========================================

class CodeAnalyzer:
    def __init__(self, root_dir):
        self.root_dir = root_dir
        self.module_map = {}  # "module_name" -> "file_path"
        self.function_map = {} # "module.func" -> {"path": str, "node": ast.FunctionDef}
        self.dependency_graph = defaultdict(set)
        self.alias_map = {}  # module_name -> canonical function key
        self._name_index = defaultdict(list)  # leaf function name -> [fully.qualified]
        
        self._scan_files()
        self._build_maps()
        self._build_aliases()

    def _scan_files(self):
        """ディレクトリ内のPythonファイルをスキャン"""
        if not os.path.exists(self.root_dir):
            raise FileNotFoundError(f"Directory '{self.root_dir}' not found.")
            
        for root, _, filenames in os.walk(self.root_dir):
            for filename in filenames:
                if filename.endswith('.py'):
                    full_path = os.path.join(root, filename)
                    rel_path = os.path.relpath(full_path, self.root_dir)
                    module_name = os.path.splitext(rel_path)[0].replace(os.sep, '.')
                    self.module_map[module_name] = full_path

    def _build_maps(self):
        """全ファイルのASTを解析し、関数定義と依存関係をマッピング"""
        print("Parsing AST for all files...")

        # --- 第1段階: 全モジュールをパースしてツリーを保持 ---
        module_trees = {}
        for module_name, file_path in self.module_map.items():
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    source = f.read()
                    module_trees[module_name] = ast.parse(source, filename=file_path)
            except Exception as e:
                print(f"Warning: Failed to parse {file_path}: {e}")

        # --- 第2段階: 関数定義を網羅的に登録 ---
        for module_name, tree in module_trees.items():
            file_path = self.module_map[module_name]
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    full_func_name = f"{module_name}.{node.name}"
                    self.function_map[full_func_name] = {
                        "path": file_path,
                        "module": module_name,
                        "name": node.name,
                        "node": node
                    }
                    # 末尾名から探索できるようインデックス化
                    self._name_index[node.name].append(full_func_name)

        # --- 第3段階: 依存関係を全関数情報を見ながら解決 ---
        def get_calls_from_node(node):
            calls = set()
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    if isinstance(child.func, ast.Name):
                        calls.add(child.func.id)
                    elif isinstance(child.func, ast.Attribute):
                        # module.func() 形式を想定して属性名を取得
                        calls.add(child.func.attr)
            return calls

        for module_name, tree in module_trees.items():
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    full_func_name = f"{module_name}.{node.name}"
                    calls = get_calls_from_node(node)
                    for call in calls:
                        local_candidate = f"{module_name}.{call}"

                        # 1. 同一モジュール内呼び出しを優先
                        if local_candidate in self.function_map and local_candidate != full_func_name:
                            self.dependency_graph[full_func_name].add(local_candidate)
                            continue

                        # 2. 末尾名が一致する別モジュールの関数を候補にする
                        for cand in self._candidate_functions_by_name(call):
                            if cand != full_func_name:
                                self.dependency_graph[full_func_name].add(cand)

    def _candidate_functions_by_name(self, leaf_name):
        return self._name_index.get(leaf_name, [])

    def _build_aliases(self):
        """モジュール名を主要関数にマッピング (splitter生成ファイル向け)"""
        module_to_funcs = defaultdict(list)

        for func_key, info in self.function_map.items():
            module_to_funcs[info["module"]].append(func_key)

        for module_name, funcs in module_to_funcs.items():
            leaf = module_name.split('.')[-1]

            same_named = [f for f in funcs if f.endswith(f".{leaf}")]
            if same_named:
                self.alias_map[module_name] = same_named[0]
            elif len(funcs) == 1:
                self.alias_map[module_name] = funcs[0]

    def resolve_symbol(self, name):
        """モジュール別名を含めて実体キーへ解決"""
        if name in self.function_map:
            return name
        if name in self.alias_map:
            return self.alias_map[name]

        # 一意に特定できる末尾名ならそれを採用（ターゲットが leaf 名だけ指定された場合に対応）
        candidates = self._candidate_functions_by_name(name)
        if len(candidates) == 1:
            return candidates[0]
        return None

    def available_symbols(self):
        return sorted(set(self.function_map.keys()) | set(self.alias_map.keys()))

    def get_function_source(self, full_func_name):
        """指定された関数のソースコードテキストを抽出"""
        resolved_name = self.resolve_symbol(full_func_name)
        if not resolved_name:
            return None
            
        info = self.function_map[resolved_name]
        file_path = info["path"]
        node = info["node"]
        
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            
        # Python 3.8+: lineno is 1-based
        start = node.lineno - 1
        end = getattr(node, 'end_lineno', start + len(node.body)) 
        
        return "".join(lines[start:end])

    def get_dependencies(self, full_func_name):
        """直接の依存関数リストを取得"""
        resolved_name = self.resolve_symbol(full_func_name)
        if not resolved_name:
            return []
        return list(self.dependency_graph.get(resolved_name, []))

    def get_dependency_closure(self, start_func_name):
        """指定関数が呼び出す全ての(推定)依存関数を再帰的に取得"""
        resolved_start = self.resolve_symbol(start_func_name)
        if not resolved_start:
            return []

        visited = set()

        def _dfs(func_name):
            for dep in self.dependency_graph.get(func_name, []):
                if dep in visited:
                    continue
                visited.add(dep)
                _dfs(dep)

        _dfs(resolved_start)
        return sorted(visited)

    def get_processing_order(self, start_func_name):
        """ターゲット関数から依存関係を再帰的に辿り、処理順序（依存先→依存元）を決定する"""
        resolved_start = self.resolve_symbol(start_func_name)
        if not resolved_start:
            return []

        visited = set()
        order = []

        def _visit(func_name):
            if func_name in visited:
                return
            visited.add(func_name)
            
            # 依存している関数を先に訪問 (DFS)
            dependencies = self.get_dependencies(func_name)
            for dep in dependencies:
                _visit(dep)
            
            # 依存先が全て処理された後に自分を追加 (Post-order / Topological Sort)
            order.append(func_name)

        _visit(resolved_start)
        return order

# ==========================================
# 3. LLM ドキュメント生成ロジック
# ==========================================

DOCUMENTATION_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "function_name": {"type": "STRING"},
        "summary": {"type": "STRING", "description": "過不足なく要約、技術的に正確に。○○を行います。具体的には...のように。最大でも400文字程度で。ただし神関数などの場合は長さの制約より正確性を優先してください。"},
        "arguments": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING"},
                    "type": {"type": "STRING", "description": "Python型ヒントまたはデータ構造"},
                    "desc": {"type": "STRING"}
                }
            }
        },
        "returns": {
            "type": "OBJECT",
            "properties": {
                "type": {"type": "STRING"},
                "desc": {"type": "STRING"}
            }
        },
        "side_effects": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "外部状態（bpy.context, global, ファイル等）への変更"
        },
        "dependencies": {
            "type": "ARRAY",
            "items": {"type": "STRING"}
        },
        "srp_analysis": {
            "type": "OBJECT",
            "properties": {
                "level": {
                    "type": "STRING",
                    "enum": ["Low", "Medium", "High"],
                    "description": "SRP(単一責任の原則)違反レベル。Low: おおよそ問題なし。Medium: 問題ありだが、これを外部からインポートするシステムから等価の修正で対応可能。High: 深刻、巨大な神関数などで、外部の構造も含めた修正が望まれる。"
                },
                "reason": {"type": "STRING", "description": "SRP違反レベルの理由。"}
            },
            "required": ["level", "reason"]
        }
    },
    "required": ["function_name", "summary", "arguments", "returns", "side_effects", "srp_analysis"]
}

def generate_docs(func_name, source_code, dependency_docs=None):
    if not source_code:
        return {"error": f"Source code not found for {func_name}"}

    prompt = f"""
あなたはPythonとBlender API (bpy) のエキスパートです。
以下の関数の技術ドキュメントをJSON形式で生成してください。
加えて、単一責任の原則（SRP）の観点からコードを評価し、違反の深刻度を分析してください。

### 対象関数: {func_name}
```python
{source_code}
```
"""
    if dependency_docs:
        prompt += "\n### 呼び出している下位関数の仕様:\n"
        prompt += "※以下の情報は確定済みのドキュメントです。この内容（特に副作用と戻り値）を前提に、対象関数の動作を解説してください。\n\n"
        for dep in dependency_docs:
            prompt += f"--- Function: {dep['function_name']} ---\n"
            # トークン節約のため、重要なフィールドのみ渡す
            clean_dep = {k: v for k, v in dep.items() if k in ['summary', 'returns', 'side_effects']}
            prompt += json.dumps(clean_dep, indent=2, ensure_ascii=False) + "\n\n"

    model = genai.GenerativeModel(
        model_name=MODEL_NAME,
        generation_config={
            "response_mime_type": "application/json",
            "response_schema": DOCUMENTATION_SCHEMA,
            "temperature": 0.1
        }
    )

    print(f"  [LLM] Generating docs for: {func_name} ...")
    try:
        response = model.generate_content(prompt)
        return json.loads(response.text)
    except Exception as e:
        # Propagate as fatal to stop the run and avoid emitting partial docs
        raise RuntimeError(f"LLM generation failed for {func_name}: {e}") from e

# ==========================================
# 4. メイン実行フロー
# ==========================================

def main():
    print(f"Initializing analyzer on: {TARGET_DIR}")
    analyzer = CodeAnalyzer(TARGET_DIR)
    
    # ターゲット関数が存在するか確認 (モジュール名でも可)
    resolved_target = analyzer.resolve_symbol(TARGET_FUNCTION)
    if not resolved_target:
        print(f"Error: Target function '{TARGET_FUNCTION}' not found in scanned files.")
        print("Available functions example:", analyzer.available_symbols()[:5])
        return

    # 再帰的に処理順序を決定 (トポロジカルソート: 葉 -> 根)
    print(f"\nResolving dependency tree for: {TARGET_FUNCTION}...")
    processing_order = analyzer.get_processing_order(TARGET_FUNCTION)
    
    print(f"Processing Order ({len(processing_order)} functions):")
    for i, func in enumerate(processing_order):
        disp = collapse_duplicate_module_func(func)
        suffix = f" [{func}]" if disp != func else ""
        print(f"  {i+1}. {disp}{suffix}")
    
    # ドキュメントストア
    doc_store = {}
    ensure_doc_dir()

    print("\n" + "="*40)
    print("STARTING RECURSIVE DOCUMENTATION GENERATION")
    print("="*40)

    for func_name in processing_order:
        # 既に生成済みかチェック
        cached_doc = load_existing_doc(func_name, analyzer=analyzer)
        if cached_doc:
            print(f"  [Cache] Using existing documentation for {func_name}")
            doc_store[func_name] = cached_doc
            continue

        # 依存関数(直接+再帰)のドキュメントを収集 (コンテキスト用)
        # processing_orderにより、依存先は既に処理済み(doc_storeにある)はず
        transitive_deps = set(analyzer.get_dependency_closure(func_name))
        dep_docs_context = []

        # 安定した順序で提示するために processing_order をフィルタリング
        for dep in processing_order:
            if dep not in transitive_deps:
                continue
            if dep in doc_store:
                dep_docs_context.append(doc_store[dep])
            else:
                # 万が一順序外の依存があった場合のフォールバック
                d = load_existing_doc(dep, analyzer=analyzer)
                if d:
                    dep_docs_context.append(d)

        source = analyzer.get_function_source(func_name)
        display_name = collapse_duplicate_module_func(func_name)
        if source:
            print(f"  [Gen] Generating docs for {display_name} (Context: {len(dep_docs_context)} deps)...")
            try:
                doc = generate_docs(display_name, source, dependency_docs=dep_docs_context)
            except RuntimeError as exc:
                print(str(exc))
                print("Aborting run due to LLM error. No file was written for the failing function.")
                return

            if doc:
                doc["function_name"] = display_name
                # ターゲット関数の場合、エイリアスとしてTARGET_FUNCTION名も登録
                extra_keys = [TARGET_FUNCTION] if func_name == resolved_target else None
                save_doc(func_name, doc, extra_keys=extra_keys, analyzer=analyzer)
                doc_store[func_name] = doc
        else:
            print(f"Warning: Source for '{func_name}' not found. Skipping.")

    # 結果出力
    print("\n" + "="*40)
    print("FINAL GENERATED DOCUMENTATION")
    print("="*40)
    
    if resolved_target in doc_store:
        final_doc = doc_store[resolved_target]
        print(json.dumps(final_doc, indent=2, ensure_ascii=False))
        
        # 保存 (テスト用)
        with open("generated_doc_test.json", "w", encoding="utf-8") as f:
            json.dump(final_doc, f, indent=2, ensure_ascii=False)
        print("\nSaved to generated_doc_test.json")
    else:
        print("Error: Target documentation could not be generated.")

if __name__ == "__main__":
    main()