import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))


def get_vertex_weight_safe(target_obj, group, vertex_index):
    """
    頂点グループからウェイトを安全に取得する。
    
    Args:
        target_obj: 対象のBlenderオブジェクト
        group: 頂点グループ
        vertex_index: 頂点インデックス
        
    Returns:
        float: ウェイト値（グループがない場合や取得に失敗した場合は0.0）
    """
    if not group:
        return 0.0
    try:
        for g in target_obj.data.vertices[vertex_index].groups:
            if g.group == group.index:
                return g.weight
    except Exception:
        return 0.0
    return 0.0
