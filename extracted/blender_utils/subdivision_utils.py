import os
import sys

from mathutils import Vector
from mathutils.bvhtree import BVHTree
from scipy.spatial import cKDTree
import bmesh
import bpy
import numpy as np
import os
import sys


# Merged from subdivide_faces.py

def subdivide_faces(obj, face_indices, cuts=1, max_distance=0.005):
    """
    指定された面（face_indices）からワールド座標系で一定距離以内にある面を細分化します。
    BVHTreeを使用して高速化を行います。
    ※Custom Split Normalsがある場合、細分化前に各頂点の平均カスタム法線を保存し、
      細分化後に各ループの最寄り元法線を補間して再設定します。
    """
    mesh = obj.data
    had_custom_normals = mesh.has_custom_normals

    if not obj or obj.type != 'MESH':
        print("無効なオブジェクトです")
        return

    if len(obj.data.vertices) == 0:
        return

    # --- 細分化前にCustom Split Normalsを保存（cKDTree版） ---
    orig_normals_per_vertex = {}
    kd = None
    if had_custom_normals:
        # 各ループを1度の走査で、頂点ごとに法線リストを作成
        temp_normals = {i: [] for i in range(len(mesh.vertices))}
        for loop in mesh.loops:
            temp_normals[loop.vertex_index].append(loop.normal)
        for v_idx, normals in temp_normals.items():
            if normals:
                avg = Vector((0.0, 0.0, 0.0))
                for n in normals:
                    avg += n
                if avg.length > 1e-8:
                    avg.normalize()
                orig_normals_per_vertex[v_idx] = avg.copy()
        # 各頂点の座標をNumPy配列にまとめ、cKDTreeを構築
        points = np.array([v.co[:] for v in mesh.vertices])
        kd = cKDTree(points)

    try:
        # --- BMeshを用いた細分化処理 ---
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.faces.ensure_lookup_table()
        
        # ワールド座標系に変換
        bm.transform(obj.matrix_world)
        
        # BVHTreeを構築
        bvh_tree = BVHTree.FromBMesh(bm)

        # 初期対象の面を取得
        initial_faces = {f for f in bm.faces if f.index in face_indices}
        
        # 距離内の面を検索するための対象面のセット
        faces_within_distance = set(initial_faces)
        
        # 各初期対象面からdistance_threshold以内の面を検索
        for f in initial_faces:
            # 面の中心点を計算
            face_center = f.calc_center_median()
            
            # 面の法線とサイズを考慮した検索範囲を設定
            # 面の最大エッジ長を計算してサーチ半径に加算
            max_edge_length = max([e.calc_length() for e in f.edges])
            search_radius = max_edge_length
            if max_edge_length > max_distance:
                search_radius = max_distance
            
            # BVHTreeで近傍の面を検索
            for (location, normal, index, distance) in bvh_tree.find_nearest_range(face_center, search_radius):
                if index is not None and index < len(bm.faces):
                    candidate_face = bm.faces[index]
                    faces_within_distance.add(candidate_face)

        # ワールド座標から元の座標系に戻す
        bm.transform(obj.matrix_world.inverted())

        # 細分化対象のエッジは、距離内の対象面に属するエッジのみ
        all_edges_candidates = {edge for f in faces_within_distance for edge in f.edges}
        
        # エッジの長さが0.004より短いものを除外
        min_edge_length = 0.004
        edges_to_subdivide = []
        
        for edge in all_edges_candidates:
            edge_length = edge.calc_length()
            if edge_length >= min_edge_length:
                edges_to_subdivide.append(edge)

        if edges_to_subdivide:
            bmesh.ops.subdivide_edges(
                bm,
                edges=edges_to_subdivide,
                cuts=cuts,
                use_grid_fill=True,
                use_single_edge=False,
                use_only_quads=True
            )

        # 対象面とその隣接面、さらにその隣接面を一度の走査で取得
        faces_to_check = set(faces_within_distance)
        # 1次隣接面を取得
        first_level_adjacent = set()
        for f in faces_within_distance:
            for edge in f.edges:
                first_level_adjacent.update(edge.link_faces)
        faces_to_check.update(first_level_adjacent)
        
        # 2次隣接面を取得
        for f in first_level_adjacent:
            for edge in f.edges:
                faces_to_check.update(edge.link_faces)

        # 五角形以上のポリゴンを三角形化
        ngons = [f for f in faces_to_check if len(f.verts) > 4]
        if ngons:
            bmesh.ops.triangulate(
                bm,
                faces=ngons,
                quad_method='BEAUTY',
                ngon_method='BEAUTY'
            )

        # BMeshの内容をメッシュに反映
        bm.to_mesh(mesh)
        mesh.update()
        bm.free()
    except Exception:
        pass  # 細分化失敗を無視
    # --- 細分化後、Custom Split Normalsを再設定（cKDTree使用） ---
    if had_custom_normals and kd is not None:
        new_loop_normals = [None] * len(mesh.loops)
        for i, loop in enumerate(mesh.loops):
            v_index = loop.vertex_index
            v_co = mesh.vertices[v_index].co
            # cKDTreeで最寄りの頂点を検索（距離, インデックスを返す）
            dist, orig_index = kd.query(v_co)
            # 保存しておいた元の法線を取得（なければ現状の法線を使用）
            new_loop_normals[i] = orig_normals_per_vertex.get(orig_index, mesh.vertices[v_index].normal)
        mesh.use_auto_smooth = True
        mesh.normals_split_custom_set(new_loop_normals)
        mesh.update()

# Merged from subdivide_breast_faces.py

def subdivide_breast_faces(target_obj, clothing_avatar_data):
    # subdivisionがTrueの場合、胸のボーンに関連する面を事前に細分化
    if clothing_avatar_data:
        breast_related_faces = set()
        
        # LeftBreastとRightBreastのボーン名を取得
        breast_bone_names = []
        for bone_mapping in clothing_avatar_data.get("humanoidBones", []):
            if bone_mapping["humanoidBoneName"] in ["LeftBreast", "RightBreast"]:
                breast_bone_names.append(bone_mapping["boneName"])
        
        # 補助ボーンも取得
        for aux_bone_group in clothing_avatar_data.get("auxiliaryBones", []):
            if aux_bone_group["humanoidBoneName"] in ["LeftBreast", "RightBreast"]:
                breast_bone_names.extend(aux_bone_group["auxiliaryBones"])
        
        # 胸のボーンに関連する頂点を特定
        breast_vertices = set()
        for bone_name in breast_bone_names:
            if bone_name in target_obj.vertex_groups:
                vertex_group = target_obj.vertex_groups[bone_name]
                for vertex in target_obj.data.vertices:
                    for group in vertex.groups:
                        if group.group == vertex_group.index and group.weight > 0.001:
                            breast_vertices.add(vertex.index)
        
        # 胸の頂点を含む面を特定
        if breast_vertices:
            for face in target_obj.data.polygons:
                if any(vertex_idx in breast_vertices for vertex_idx in face.vertices):
                    breast_related_faces.add(face.index)
            
            if breast_related_faces:
                print(f"Subdividing {len(breast_related_faces)} breast-related faces...")
                subdivide_faces(target_obj, list(breast_related_faces), cuts=1)

# Merged from subdivide_long_edges.py

def subdivide_long_edges(obj, min_edge_length=0.005, max_edge_length_ratio=2.0, cuts=1):
    """
    指定されたオブジェクトの中央値エッジ長より指定された倍率以上のエッジを細分化します。
    """
    mesh = obj.data
    had_custom_normals = mesh.has_custom_normals

    if not obj or obj.type != 'MESH':
        print("無効なオブジェクトです")
        return

    if len(obj.data.vertices) == 0:
        return

    # --- 細分化前にCustom Split Normalsを保存（cKDTree版） ---
    orig_normals_per_vertex = {}
    kd = None
    if had_custom_normals:
        # 各ループを1度の走査で、頂点ごとに法線リストを作成
        temp_normals = {i: [] for i in range(len(mesh.vertices))}
        for loop in mesh.loops:
            temp_normals[loop.vertex_index].append(loop.normal)
        for v_idx, normals in temp_normals.items():
            if normals:
                avg = Vector((0.0, 0.0, 0.0))
                for n in normals:
                    avg += n
                if avg.length > 1e-8:
                    avg.normalize()
                orig_normals_per_vertex[v_idx] = avg.copy()
        # 各頂点の座標をNumPy配列にまとめ、cKDTreeを構築
        points = np.array([v.co[:] for v in mesh.vertices])
        kd = cKDTree(points)

    try:
        # --- BMeshを用いた細分化処理 ---
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.edges.ensure_lookup_table()
        
        # 全エッジの長さを計算して中央値を求める
        edge_lengths = []
        for edge in bm.edges:
            if edge.calc_length() >= min_edge_length:
                edge_lengths.append(edge.calc_length())
        
        if not edge_lengths:
            print("エッジが見つかりません")
            bm.free()
            return
            
        # エッジ長をソートして中央値を計算
        edge_lengths.sort()
        n = len(edge_lengths)
        if n % 2 == 0:
            # 偶数個の場合は中央2つの値の平均
            median_edge_length = (edge_lengths[n//2 - 1] + edge_lengths[n//2]) / 2
        else:
            # 奇数個の場合は中央の値
            median_edge_length = edge_lengths[n//2]
            
        threshold_length = median_edge_length * max_edge_length_ratio
        
        print(f"細分化閾値: {threshold_length:.6f} (中央値の{max_edge_length_ratio}倍)")
        
        # 閾値以上の長さのエッジを特定
        edges_to_subdivide = []
        for edge in bm.edges:
            if edge.calc_length() >= threshold_length:
                edges_to_subdivide.append(edge)
        
        print(f"細分化対象エッジ数: {len(edges_to_subdivide)} / {len(bm.edges)}")

        if edges_to_subdivide:
            bmesh.ops.subdivide_edges(
                bm,
                edges=edges_to_subdivide,
                cuts=cuts,
                use_grid_fill=True,
                use_single_edge=False,
                use_only_quads=False
            )
            print(f"エッジを{cuts}回細分化しました")

        # BMeshの内容をメッシュに反映
        bm.to_mesh(mesh)
        mesh.update()
        bm.free()
    except Exception as e:
        if 'bm' in locals():
            bm.free()

    # --- 細分化後、Custom Split Normalsを再設定（cKDTree使用） ---
    if had_custom_normals and kd is not None:
        new_loop_normals = [None] * len(mesh.loops)
        for i, loop in enumerate(mesh.loops):
            v_index = loop.vertex_index
            v_co = mesh.vertices[v_index].co
            # cKDTreeで最寄りの頂点を検索（距離, インデックスを返す）
            dist, orig_index = kd.query(v_co)
            # 保存しておいた元の法線を取得（なければ現状の法線を使用）
            new_loop_normals[i] = orig_normals_per_vertex.get(orig_index, mesh.vertices[v_index].normal)
        mesh.use_auto_smooth = True
        mesh.normals_split_custom_set(new_loop_normals)
        mesh.update()

# Merged from subdivide_selected_vertices.py

def subdivide_selected_vertices(obj_name, vertex_indices, level=2):
    """
    特定のメッシュの選択された頂点を細分化する
    
    引数:
        obj_name (str): 操作対象のオブジェクト名
        vertex_indices (list): 選択する頂点のインデックスリスト
        cuts (int): 細分化の分割数
    """
    # アクティブオブジェクトの設定
    bpy.ops.object.mode_set(mode='OBJECT')
    obj = bpy.data.objects.get(obj_name)
    
    if obj is None:
        print(f"オブジェクト '{obj_name}' が見つかりません")
        return
    
    # オブジェクトを選択してアクティブに
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    
    # 編集モードに切り替え
    bpy.ops.object.mode_set(mode='EDIT')
    
    # bmeshを取得
    me = obj.data
    bm = bmesh.from_edit_mesh(me)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    
    # すべての選択を解除
    for v in bm.verts:
        v.select = False
    for e in bm.edges:
        e.select = False
    for f in bm.faces:
        f.select = False
    
    # 指定された頂点を選択
    for idx in vertex_indices:
        if idx < len(bm.verts):
            bm.verts[idx].select = True
    
    # 選択された頂点「同士」で構成されるエッジのみを選択
    # つまり、エッジの両端の頂点が両方とも選択された頂点リストに含まれる場合のみ選択
    selected_verts = set(bm.verts[idx] for idx in vertex_indices if idx < len(bm.verts))
    connected_edges = []
    
    for e in bm.edges:
        # エッジの両端の頂点が両方とも選択された頂点セットに含まれる場合のみ選択
        if e.verts[0] in selected_verts and e.verts[1] in selected_verts:
            e.select = True
            connected_edges.append(e)
    
    # 変更を適用
    bmesh.update_edit_mesh(me)
    
    # 細分化操作
    if connected_edges:
        for _ in range(level):
            bpy.ops.mesh.subdivide(number_cuts=1)
    # else: 細分化対象エッジなし
    
    # オブジェクトモードに戻る
    bpy.ops.object.mode_set(mode='OBJECT')
    obj.data.update()