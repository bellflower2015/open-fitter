import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import bmesh
import bpy
from algo_utils.mesh_topology_utils import check_edge_direction_similarity
from algo_utils.bone_group_utils import (
    get_humanoid_and_auxiliary_bone_groups,
)
from math_utils.weight_utils import (
    calculate_weight_pattern_similarity,
)
from mathutils.kdtree import KDTree


def create_overlapping_vertices_attributes(clothing_meshes, base_avatar_data, distance_threshold=0.0001, edge_angle_threshold=3, weight_similarity_threshold=0.1, overlap_attr_name="Overlapped", world_pos_attr_name="OriginalWorldPosition"):
    """
    ワールド座標上でほぼ重なっていて、ウェイトパターンが類似している頂点を検出し、
    カスタム頂点属性としてフラグ(1.0)を設定する。またワールド頂点座標も別の属性として保存する。
    
    Parameters:
        clothing_meshes: 処理対象の衣装メッシュのリスト
        base_avatar_data: ベースアバターデータ
        distance_threshold: 重なっていると判定する距離の閾値
        weight_similarity_threshold: ウェイトパターンの類似性閾値（小さいほど厳密）
        overlap_attr_name: 重なり頂点フラグ用のカスタム属性の名前
        world_pos_attr_name: ワールド座標を保存するカスタム属性の名前
    """
    print(f"Creating custom attributes for overlapping vertices with similar weight patterns...")
    
    # チェック対象の頂点グループを取得
    target_groups = get_humanoid_and_auxiliary_bone_groups(base_avatar_data)
    
    # 各メッシュに対して処理
    for mesh_obj in clothing_meshes:
        depsgraph = bpy.context.evaluated_depsgraph_get()
        eval_obj = mesh_obj.evaluated_get(depsgraph)
        mesh = eval_obj.data
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        
        # 頂点インデックスのマッピングを作成（BMesh内のインデックス → 元のメッシュのインデックス）
        vert_indices = {v.index: i for i, v in enumerate(bm.verts)}
        
        # 頂点データを収集
        all_vertices = []
        for vert_idx, vert in enumerate(bm.verts):
            # 頂点のワールド座標を計算
            world_pos = mesh_obj.matrix_world @ vert.co
            
            # 頂点に接続するエッジの方向ベクトルを収集
            edge_directions = []
            bm_vert = bm.verts[vert_idx]
            for edge in bm_vert.link_edges:
                other_vert = edge.other_vert(bm_vert)
                direction = (other_vert.co - bm_vert.co).normalized()
                edge_directions.append(direction)
            
            # 対象グループのウェイトを収集
            weights = {}
            orig_vert = mesh_obj.data.vertices[vert_indices[vert_idx]]
            for group_name in target_groups:
                if group_name in mesh_obj.vertex_groups:
                    group = mesh_obj.vertex_groups[group_name]
                    for g in orig_vert.groups:
                        if g.group == group.index:
                            weights[group_name] = g.weight
                            break
            
            # 頂点データを保存
            all_vertices.append({
                'vert_idx': vert_idx,
                'world_pos': world_pos,
                'edge_directions': edge_directions,
                'weights': weights
            })
        
        # KDTreeを構築して近接頂点を効率的に検索
        positions = [v['world_pos'] for v in all_vertices]
        kdtree = KDTree(len(positions))
        for i, pos in enumerate(positions):
            kdtree.insert(pos, i)
        kdtree.balance()
        
        # 重なり頂点用のカスタム属性を作成または取得
        if overlap_attr_name not in mesh_obj.data.attributes:
            mesh_obj.data.attributes.new(name=overlap_attr_name, type='FLOAT', domain='POINT')
        overlap_attr = mesh_obj.data.attributes[overlap_attr_name]
        
        # ワールド座標用のカスタム属性を作成または取得
        if world_pos_attr_name not in mesh_obj.data.attributes:
            mesh_obj.data.attributes.new(name=world_pos_attr_name, type='FLOAT_VECTOR', domain='POINT')
        pos_attr = mesh_obj.data.attributes[world_pos_attr_name]
        
        # 初期値を設定 (重なり属性は0、ワールド座標は現在の位置)
        for i, vertex in enumerate(mesh_obj.data.vertices):
            overlap_attr.data[i].value = 0.0
            world_position = mesh_obj.matrix_world @ vertex.co
            pos_attr.data[i].vector = world_position
        
        # 重なっている頂点を検出してフラグを設定
        processed = set()  # 処理済みの頂点インデックスを記録
        cluster_id = 0  # クラスタID（デバッグ用）
        
        for i, vert_data in enumerate(all_vertices):
            mesh_vertex_idx = vert_indices[all_vertices[i]['vert_idx']]
            world_pos = all_vertices[i]['world_pos']
            pos_attr.data[mesh_vertex_idx].vector = world_pos  # ワールド座標を保存

            if i in processed:
                continue
            
            # 近接頂点を検索
            overlapping_indices = []
            for (co, idx, dist) in kdtree.find_range(vert_data['world_pos'], distance_threshold):
                if idx != i and idx not in processed:  # 自分自身と処理済みの頂点は除外
                    # エッジ方向の類似性をチェック
                    if check_edge_direction_similarity(vert_data['edge_directions'], all_vertices[idx]['edge_directions'], edge_angle_threshold):
                        # ウェイトパターンの類似性をチェック
                        similarity = calculate_weight_pattern_similarity(
                            vert_data['weights'], all_vertices[idx]['weights'])
                        
                        # 類似性が閾値以上の場合のみ追加
                        if similarity >= (1.0 - weight_similarity_threshold):
                            overlapping_indices.append(idx)
            
            if not overlapping_indices:
                continue
            
            # 重なっている頂点グループを含める
            overlapping_indices.append(i)
            processed.add(i)
            
            
            # 重なっている頂点の属性を設定
            for vert_idx in overlapping_indices:
                mesh_vertex_idx = vert_indices[all_vertices[vert_idx]['vert_idx']]
                overlap_attr.data[mesh_vertex_idx].value = 1.0  # 重なり検出フラグを設定
                processed.add(vert_idx)
            
            cluster_id += 1
        
        # BMeshを解放
        bm.free()
        
        mesh_obj.data.update()
        
        print(f"Created custom attributes '{overlap_attr_name}' and '{world_pos_attr_name}' for {mesh_obj.name} with {cluster_id} overlapping vertex clusters")
        print(f"Distance threshold: {distance_threshold}")
        print(f"Weight similarity threshold: {weight_similarity_threshold}")
