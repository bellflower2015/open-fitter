"""
Print文・Time測定の自動クリーンアップスクリプト

ASTベースで安全にコードを解析し、以下を削除/整理:
1. 単純なprint文（デバッグ用）
2. time.time()による細かい時間測定
3. 処理時間のprint（例: f"処理: {end - start:.2f}秒"）

保持するもの:
- Status: で始まるprint（進捗表示用）
- Progress: で始まるprint（進捗バー用）
- Error/Warning を含むprint（エラー報告）
- ステージの開始/終了を示す重要なprint
"""

import ast
import re
import os
import sys
from pathlib import Path
from typing import List, Set, Tuple


class PrintAnalyzer(ast.NodeVisitor):
    """print文を解析して分類する"""
    
    def __init__(self, source_lines: List[str]):
        self.source_lines = source_lines
        self.prints_to_remove: List[Tuple[int, int, str]] = []  # (start_line, end_line, reason)
        self.prints_to_keep: List[Tuple[int, str]] = []  # (line, reason)
        self.time_assignments: Set[int] = set()  # time.time()の代入行
        self.time_vars: Set[str] = set()  # time変数名
        
    def visit_Expr(self, node):
        """式文（print文など）を処理"""
        if isinstance(node.value, ast.Call):
            self._check_print_call(node)
        self.generic_visit(node)
        
    def visit_Assign(self, node):
        """代入文を処理（time.time()の検出）"""
        if self._is_time_call(node.value):
            # time.time()の代入を記録
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.time_vars.add(target.id)
                    self.time_assignments.add(node.lineno)
        self.generic_visit(node)
        
    def _is_time_call(self, node) -> bool:
        """time.time()呼び出しかどうか"""
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if node.func.attr == 'time':
                    if isinstance(node.func.value, ast.Name) and node.func.value.id == 'time':
                        return True
                    if isinstance(node.func.value, ast.Attribute) and node.func.value.attr == 'time_module':
                        return True
        return False
        
    def _check_print_call(self, node):
        """print呼び出しを分類"""
        call = node.value
        if not (isinstance(call.func, ast.Name) and call.func.id == 'print'):
            return
            
        line_no = node.lineno
        line_content = self.source_lines[line_no - 1] if line_no <= len(self.source_lines) else ""
        
        # 保持すべきパターン
        keep_patterns = [
            (r'Status:', 'progress_status'),
            (r'Progress:', 'progress_bar'),
            (r'Error', 'error_message'),
            (r'Warning', 'warning_message'),
            (r'Exception', 'exception_message'),
            (r'処理完了', 'completion_message'),
            (r'=== Stage', 'stage_marker'),
        ]
        
        for pattern, reason in keep_patterns:
            if re.search(pattern, line_content, re.IGNORECASE):
                self.prints_to_keep.append((line_no, reason))
                return
                
        # 削除すべきパターン
        remove_patterns = [
            (r':\s*\{.*time.*-.*\}', 'time_measurement'),  # 時間測定print
            (r':\s*\{.*\.2f\}秒', 'time_measurement_jp'),  # 日本語時間測定
            (r'秒$', 'time_suffix'),  # 秒で終わる
            (r'^\s*print\(f"[^"]*:\s*\{', 'debug_variable'),  # 変数デバッグ
            (r'config_pair', 'config_debug'),  # config_pairのデバッグ
            (r'Found \d+', 'found_count'),  # カウント報告
            (r'Processing', 'processing_debug'),  # 処理中デバッグ
            (r'Applying', 'applying_debug'),  # 適用中デバッグ
            (r'Loading', 'loading_debug'),  # ロード中デバッグ
            (r'^\s*print\(f"', 'fstring_debug'),  # f-stringデバッグ（汎用）
        ]
        
        for pattern, reason in remove_patterns:
            if re.search(pattern, line_content):
                self.prints_to_remove.append((line_no, line_no, reason))
                return
                
        # 判断がつかないものはとりあえず保持
        self.prints_to_keep.append((line_no, 'unknown'))


class TimeCleanupTransformer(ast.NodeTransformer):
    """時間測定関連のコードを削除"""
    
    def __init__(self, time_vars: Set[str]):
        self.time_vars = time_vars
        self.lines_to_remove: Set[int] = set()
        
    def visit_Assign(self, node):
        """time.time()代入を削除対象としてマーク"""
        if self._is_time_call(node.value):
            # ただし、ステージ開始時の重要なものは保持
            for target in node.targets:
                if isinstance(target, ast.Name):
                    # start_time, overall_start_time は保持
                    if target.id in ('start_time', 'overall_start_time'):
                        return node
            self.lines_to_remove.add(node.lineno)
            return None
        return node
        
    def _is_time_call(self, node) -> bool:
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if node.func.attr == 'time':
                    return True
        return False


def analyze_file(filepath: Path) -> dict:
    """ファイルを解析してprint/time情報を返す"""
    with open(filepath, 'r', encoding='utf-8') as f:
        source = f.read()
        source_lines = source.splitlines()
    
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return {'error': str(e)}
    
    analyzer = PrintAnalyzer(source_lines)
    analyzer.visit(tree)
    
    return {
        'prints_to_remove': analyzer.prints_to_remove,
        'prints_to_keep': analyzer.prints_to_keep,
        'time_assignments': analyzer.time_assignments,
        'time_vars': analyzer.time_vars,
        'total_prints': len(analyzer.prints_to_remove) + len(analyzer.prints_to_keep)
    }


def remove_lines_safely(filepath: Path, lines_to_remove: Set[int], dry_run: bool = True) -> str:
    """指定行を安全に削除"""
    with open(filepath, 'r', encoding='utf-8') as f:
        source_lines = f.readlines()
    
    new_lines = []
    for i, line in enumerate(source_lines, 1):
        if i not in lines_to_remove:
            new_lines.append(line)
        else:
            # 空行でない場合のみ削除をログ
            if line.strip():
                pass  # 削除
    
    new_source = ''.join(new_lines)
    
    if not dry_run:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_source)
    
    return new_source


def process_directory(directory: Path, dry_run: bool = True):
    """ディレクトリ内の全Pythonファイルを処理"""
    results = {
        'files_processed': 0,
        'prints_removed': 0,
        'prints_kept': 0,
        'time_removed': 0,
        'details': []
    }
    
    for pyfile in directory.rglob('*.py'):
        # このスクリプト自体は除外
        if pyfile.name == 'cleanup_prints.py':
            continue
            
        analysis = analyze_file(pyfile)
        
        if 'error' in analysis:
            print(f"Error parsing {pyfile}: {analysis['error']}")
            continue
            
        results['files_processed'] += 1
        results['prints_removed'] += len(analysis['prints_to_remove'])
        results['prints_kept'] += len(analysis['prints_to_keep'])
        results['time_removed'] += len(analysis['time_assignments'])
        
        if analysis['prints_to_remove'] or analysis['time_assignments']:
            results['details'].append({
                'file': str(pyfile),
                'to_remove': len(analysis['prints_to_remove']),
                'to_keep': len(analysis['prints_to_keep']),
                'time_vars': len(analysis['time_assignments'])
            })
    
    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Cleanup debug prints and time measurements')
    parser.add_argument('--dry-run', action='store_true', default=True,
                       help='Analyze only, do not modify files')
    parser.add_argument('--apply', action='store_true',
                       help='Actually apply changes')
    parser.add_argument('--file', type=str, help='Process single file')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Show detailed output')
    args = parser.parse_args()
    
    dry_run = not args.apply
    
    if args.file:
        filepath = Path(args.file)
        analysis = analyze_file(filepath)
        print(f"\n=== Analysis of {filepath} ===")
        print(f"Total prints: {analysis['total_prints']}")
        print(f"Prints to remove: {len(analysis['prints_to_remove'])}")
        print(f"Prints to keep: {len(analysis['prints_to_keep'])}")
        print(f"Time assignments: {len(analysis['time_assignments'])}")
        
        if args.verbose:
            print("\n--- To Remove ---")
            for line, _, reason in analysis['prints_to_remove']:
                print(f"  Line {line}: {reason}")
            print("\n--- To Keep ---")
            for line, reason in analysis['prints_to_keep']:
                print(f"  Line {line}: {reason}")
    else:
        directory = Path(__file__).parent / 'extracted'
        results = process_directory(directory, dry_run)
        
        print("\n" + "="*60)
        print("PRINT/TIME CLEANUP ANALYSIS")
        print("="*60)
        print(f"Files processed: {results['files_processed']}")
        print(f"Prints to remove: {results['prints_removed']}")
        print(f"Prints to keep: {results['prints_kept']}")
        print(f"Time assignments to remove: {results['time_removed']}")
        print(f"\nMode: {'DRY RUN (no changes)' if dry_run else 'APPLYING CHANGES'}")
        
        if args.verbose and results['details']:
            print("\n--- Files with changes ---")
            for detail in sorted(results['details'], key=lambda x: x['to_remove'], reverse=True):
                print(f"  {detail['file']}")
                print(f"    Remove: {detail['to_remove']} prints, {detail['time_vars']} time vars")
                print(f"    Keep: {detail['to_keep']} prints")


if __name__ == '__main__':
    main()
