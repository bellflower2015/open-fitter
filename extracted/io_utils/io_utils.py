import os
import sys

from math_utils.geometry_utils import calculate_vertices_world
import bpy
import json
import numpy as np
import os
import sys


# Merged from file_io.py

def export_fbx(filepath: str, selected_only: bool = True) -> None:
    """Export selected objects to FBX."""
    try:
        bpy.ops.export_scene.fbx(
            filepath=filepath,
            use_selection=selected_only,
            apply_scale_options='FBX_SCALE_ALL',
            apply_unit_scale=True,
            add_leaf_bones=False,
            axis_forward='-Z', axis_up='Y'
        )
    except Exception as e:
        raise Exception(f"Failed to export FBX: {str(e)}")


def import_base_fbx(filepath: str, automatic_bone_orientation: bool = False) -> None:
    """Import base avatar FBX file."""
    try:
        bpy.ops.import_scene.fbx(
            filepath=filepath,
            use_anim=False,  # アニメーションの読み込みを無効化
            automatic_bone_orientation=automatic_bone_orientation
        )
    except Exception as e:
        raise Exception(f"Failed to import base FBX: {str(e)}")


def load_base_file(filepath: str) -> None:
    """Load the base Blender file containing the character model."""
    try:
        bpy.ops.wm.open_mainfile(filepath=filepath)
    except Exception as e:
        raise Exception(f"Failed to load base file: {str(e)}")

# Merged from avatar_data.py

"""
アバターデータの読み込みユーティリティ
"""



def load_avatar_data(filepath: str) -> dict:
    """Load and parse avatar data from JSON file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        raise Exception(f"Failed to load avatar data: {str(e)}")


def load_avatar_data_for_blendshape_analysis(avatar_data_path: str) -> dict:
    """
    BlendShape分析用にアバターデータを読み込む
    
    Parameters:
        avatar_data_path: アバターデータファイルのパス
        
    Returns:
        dict: アバターデータ（エラー時は空辞書）
    """
    try:
        with open(avatar_data_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        return {}

# Merged from load_cloth_metadata.py

def load_cloth_metadata(filepath):
    """
    変形後のワールド座標に基づいてClothメタデータをロード
    
    Returns:
        Tuple[dict, dict]: (メタデータのマッピング, Unity頂点インデックスからBlender頂点インデックスへのマッピング)
    """
    from algo_utils.search_utils import find_closest_vertices_brute_force

    if not filepath or not os.path.exists(filepath):
        return {}, {}
        
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
            metadata_by_mesh = {}
            vertex_index_mapping = {}  # Unity頂点インデックス -> Blender頂点インデックスのマッピング
            
            # シーンの評価を最新の状態に更新
            depsgraph = bpy.context.evaluated_depsgraph_get()
            depsgraph.update()
            
            for metadata in data.get('clothMetadata', []):
                mesh_name = metadata['meshName']
                mesh_obj = None
                
                # メッシュを探す
                for obj in bpy.data.objects:
                    if obj.type == 'MESH' and obj.name == mesh_name:
                        mesh_obj = obj
                        break
                
                if not mesh_obj:
                    print(f"[Warning] Mesh {mesh_name} not found")
                    continue
                
                # Unityのワールド座標をBlenderのワールド座標に変換
                unity_positions = []
                max_distances = []
                for i, vertex_data in enumerate(metadata.get('vertexData', [])):
                    pos = vertex_data['position']
                    # Unity座標系からBlender座標系への変換
                    unity_positions.append([
                        -pos['x'],      # Unity X → Blender X
                        -pos['z'],      # Unity Y → Blender Z
                        pos['y']       # Unity Z → Blender Y
                    ])
                    max_distances.append(vertex_data['maxDistance'])
                
                # 一括で最近接頂点を検索
                vertices_world = calculate_vertices_world(mesh_obj)
                vertex_mappings = find_closest_vertices_brute_force(
                    unity_positions,
                    vertices_world,
                    max_distance=0.0005
                )
                
                # 結果を頂点インデックスとmaxDistanceのマッピングに変換
                vertex_max_distances = {}
                mesh_vertex_mapping = {}  # このメッシュのUnity -> Blenderマッピング
                
                for unity_idx, blender_idx in sorted(vertex_mappings.items()):
                    if unity_idx is not None and blender_idx is not None:
                        vertex_max_distances[str(blender_idx)] = max_distances[unity_idx]
                        mesh_vertex_mapping[unity_idx] = blender_idx
                
                metadata_by_mesh[mesh_name] = vertex_max_distances
                vertex_index_mapping[mesh_name] = mesh_vertex_mapping
                
                print(f"Processed {len(vertex_max_distances)} vertices for mesh {mesh_name}")
                # マッピングできなかった頂点を特定
                mapped_indices = set(int(idx) for idx in vertex_max_distances.keys())
                unmapped_indices = set(range(len(vertices_world))) - mapped_indices
                
                if unmapped_indices:
                    print(f"[Warning] Could not map {len(unmapped_indices)} vertices")
                    
                    # デバッグ用の頂点グループを作成
                    debug_group_name = "DEBUG_UnmappedVertices"
                    if debug_group_name in mesh_obj.vertex_groups:
                        mesh_obj.vertex_groups.remove(mesh_obj.vertex_groups[debug_group_name])
                    debug_group = mesh_obj.vertex_groups.new(name=debug_group_name)
                    
                    # マッピングできなかった頂点をグループに追加
                    for idx in unmapped_indices:
                        debug_group.add([idx], 1.0, 'REPLACE')
            return metadata_by_mesh, vertex_index_mapping
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {}, {}

# Merged from load_deformation_field_num_steps.py

def load_deformation_field_num_steps(field_file_path: str, config_dir: str) -> int:
    """
    変形フィールドファイルからnum_stepsを読み込む
    
    Parameters:
        field_file_path: 変形フィールドファイルのパス（相対パス可）
        config_dir: 設定ファイルのディレクトリ
        
    Returns:
        int: num_stepsの値、読み込めない場合は1
    """
    try:
        # 相対パスの場合は絶対パスに変換
        if not os.path.isabs(field_file_path):
            field_file_path = os.path.join(config_dir, field_file_path)
        
        if os.path.exists(field_file_path):
            field_data = np.load(field_file_path, allow_pickle=True)
            return int(field_data.get('num_steps', 1))
        else:
            return 1
    except Exception as e:
        return 1

# Merged from load_mesh_material_data.py

def load_mesh_material_data(filepath):
    """
    メッシュマテリアルデータを読み込み、Blenderのメッシュにマテリアルを設定
    
    Args:
        filepath: メッシュマテリアルデータのJSONファイルパス
    """
    from algo_utils.search_utils import find_material_index_from_faces

    if not filepath or not os.path.exists(filepath):
        print("[Warning] Mesh material data file not found or not specified")
        return
        
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
            for mesh_data in data.get('meshMaterials', []):
                mesh_name = mesh_data['meshName']
                
                # Blenderでメッシュオブジェクトを検索
                mesh_obj = None
                for obj in bpy.data.objects:
                    if obj.type == 'MESH' and obj.name == mesh_name:
                        mesh_obj = obj
                        break
                
                if not mesh_obj:
                    print(f"[Warning] Mesh {mesh_name} not found in Blender scene")
                    continue
                
                # 各サブメッシュを処理
                for sub_mesh_idx, sub_mesh_data in enumerate(mesh_data['subMeshes']):
                    material_name = sub_mesh_data['materialName']
                    faces_data = sub_mesh_data['faces']
                    
                    if not faces_data:
                        continue
                        
                    # マテリアルを作成または取得
                    material = bpy.data.materials.get(material_name)
                    if not material:
                        material = bpy.data.materials.new(name=material_name)
                        # デフォルトのマテリアル設定
                        material.use_nodes = True
                    # 面から該当するマテリアルインデックスを特定し、そのスロットのマテリアルを入れ替え
                    material_index = find_material_index_from_faces(mesh_obj, faces_data)
                    if material_index is not None:
                        # メッシュにマテリアルスロットが不足している場合は追加
                        while len(mesh_obj.data.materials) <= material_index:
                            mesh_obj.data.materials.append(None)
                        
                        # 該当するマテリアルスロットを入れ替え
                        mesh_obj.data.materials[material_index] = material
                    
    except Exception:
        pass  # マテリアル読み込み失敗を無視

# Merged from load_vertex_group.py

def load_vertex_group(obj, filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        payload = json.load(f)

    group_name = payload.get("vertex_group_name")
    weights = payload.get("weights", [])
    if not group_name:
        return group_name

    vg = obj.vertex_groups.get(group_name)
    if vg is None:
        vg = obj.vertex_groups.new(name=group_name)
    else:
        indices = [v.index for v in obj.data.vertices]
        vg.remove(indices)

    missing_vertices = []
    for record in weights:
        vidx = record.get("vertex_index")
        weight = record.get("weight")
        if vidx is None or weight is None:
            continue
        if vidx >= len(obj.data.vertices):
            missing_vertices.append(vidx)
            continue
        vg.add([vidx], weight, 'REPLACE')

    obj.vertex_groups.active = vg
    return group_name

# Merged from pose_state.py

def save_pose_state(armature_obj: bpy.types.Object) -> dict:
    """
    アーマチュアの現在のポーズ状態を保存する
    
    Parameters:
        armature_obj: アーマチュアオブジェクト
        
    Returns:
        保存されたポーズ状態のディクショナリ
    """
    if not armature_obj or armature_obj.type != 'ARMATURE':
        return None
    
    pose_state = {}
    for bone in armature_obj.pose.bones:
        pose_state[bone.name] = {
            'matrix': bone.matrix.copy(),
            'location': bone.location.copy(),
            'rotation_euler': bone.rotation_euler.copy(),
            'rotation_quaternion': bone.rotation_quaternion.copy(),
            'scale': bone.scale.copy()
        }
    
    return pose_state


def store_pose_globally(armature_obj: bpy.types.Object) -> None:
    """
    グローバル変数にポーズ状態を保存する
    
    Parameters:
        armature_obj: アーマチュアオブジェクト
    """
    global _saved_pose_state
    _saved_pose_state = save_pose_state(armature_obj)

# Merged from shape_key_state.py

"""
シェイプキー状態の保存・復元ユーティリティ
"""



def save_shape_key_state(mesh_obj: bpy.types.Object) -> dict:
    """
    メッシュオブジェクトのシェイプキー状態を保存する
    
    Parameters:
        mesh_obj: メッシュオブジェクト
        
    Returns:
        保存されたシェイプキー状態のディクショナリ
    """
    if not mesh_obj or not mesh_obj.data.shape_keys:
        return {}
    
    shape_key_state = {}
    for key_block in mesh_obj.data.shape_keys.key_blocks:
        shape_key_state[key_block.name] = key_block.value
    
    return shape_key_state


def restore_shape_key_state(mesh_obj: bpy.types.Object, shape_key_state: dict) -> None:
    """
    メッシュオブジェクトのシェイプキー状態を復元する
    
    Parameters:
        mesh_obj: メッシュオブジェクト
        shape_key_state: 復元するシェイプキー状態のディクショナリ
    """
    if not mesh_obj or not mesh_obj.data.shape_keys or not shape_key_state:
        return
    
    for key_name, value in shape_key_state.items():
        if key_name in mesh_obj.data.shape_keys.key_blocks:
            mesh_obj.data.shape_keys.key_blocks[key_name].value = value

# Merged from vertex_weights_io.py

def save_vertex_weights(mesh_obj: bpy.types.Object) -> dict:
    """
    オブジェクトの全頂点グループのウェイトを記録する（空のグループも含む）
    
    Parameters:
        mesh_obj: メッシュオブジェクト
        
    Returns:
        保存されたウェイト情報のディクショナリ（vertex_weights、existing_groups、vertex_ids）
    """
    weights_data = {
        'vertex_weights': {},
        'existing_groups': set(),
        'vertex_ids': {}
    }
    
    # 全ての既存の頂点グループ名を記録
    for group in mesh_obj.vertex_groups:
        weights_data['existing_groups'].add(group.name)
    
    # 頂点に整数型のカスタム属性を作成（既に存在する場合は削除して再作成）
    mesh = mesh_obj.data
    custom_attr_name = "original_vertex_id"
    
    # 既存のカスタム属性を削除
    if custom_attr_name in mesh.attributes:
        mesh.attributes.remove(mesh.attributes[custom_attr_name])
    
    # 新しい整数型カスタム属性を作成
    custom_attr = mesh.attributes.new(name=custom_attr_name, type='INT', domain='POINT')
    
    # 各頂点のウェイトと頂点IDを記録
    for vert in mesh.vertices:
        vertex_weights = {}
        for group in vert.groups:
            group_name = mesh_obj.vertex_groups[group.group].name
            vertex_weights[group_name] = group.weight
        
        # 頂点のウェイトを記録（空の場合も記録）
        weights_data['vertex_weights'][vert.index] = vertex_weights
        
        # カスタム属性に現在の頂点IDを設定
        custom_attr.data[vert.index].value = vert.index
        
        # weights_dataにも頂点IDを記録
        weights_data['vertex_ids'][vert.index] = vert.index
    
    
    return weights_data


def restore_vertex_weights(mesh_obj: bpy.types.Object, weights_data: dict) -> None:
    """
    保存されたウェイト情報を使って頂点グループのウェイトを復元する
    カスタム属性を使用して頂点IDの対応を管理
    
    Parameters:
        mesh_obj: メッシュオブジェクト
        weights_data: save_vertex_weights()で保存されたウェイト情報
    """
    vertex_weights = weights_data['vertex_weights']
    original_groups = weights_data['existing_groups']
    saved_vertex_ids = weights_data.get('vertex_ids', {})
    
    # 現在存在するグループのうち、元々存在しなかったグループを削除
    current_groups = set(group.name for group in mesh_obj.vertex_groups)
    groups_to_remove = current_groups - original_groups
    
    for group_name in groups_to_remove:
        if group_name in mesh_obj.vertex_groups:
            mesh_obj.vertex_groups.remove(mesh_obj.vertex_groups[group_name])
    
    # 元々存在していたグループが削除されている場合は再作成
    for group_name in original_groups:
        if group_name not in mesh_obj.vertex_groups:
            mesh_obj.vertex_groups.new(name=group_name)
    
    # まず全ての頂点グループから全頂点を削除
    for group in mesh_obj.vertex_groups:
        group.remove(list(range(len(mesh_obj.data.vertices))))
    
    # カスタム属性から頂点IDの対応を取得
    mesh = mesh_obj.data
    custom_attr_name = "original_vertex_id"
    
    if custom_attr_name not in mesh.attributes:
        print(f"[Warning] Custom attribute '{custom_attr_name}' not found in {mesh_obj.name}. Using direct index mapping.")
        # カスタム属性がない場合は従来の方法でインデックスを直接使用
        for vert_index, vertex_weights_dict in vertex_weights.items():
            if vert_index < len(mesh.vertices):
                for group_name, weight in vertex_weights_dict.items():
                    if group_name in mesh_obj.vertex_groups:
                        group = mesh_obj.vertex_groups[group_name]
                        group.add([vert_index], weight, 'REPLACE')
        return
    
    # カスタム属性を取得
    custom_attr = mesh.attributes[custom_attr_name]
    
    # 現在の頂点の元の頂点IDを取得してマッピングを作成
    current_to_original_mapping = {}
    for current_vert in mesh.vertices:
        original_id = custom_attr.data[current_vert.index].value
        current_to_original_mapping[current_vert.index] = original_id
    
    print(f"Restoring vertex weights using custom attribute mapping for {len(mesh.vertices)} vertices in {mesh_obj.name}")
    
    # 保存されたウェイトを復元（カスタム属性を使用して対応を取る）
    restored_count = 0
    for current_vert_index, original_vert_id in current_to_original_mapping.items():
        if original_vert_id in vertex_weights:
            vertex_weights_dict = vertex_weights[original_vert_id]
            for group_name, weight in vertex_weights_dict.items():
                if group_name in mesh_obj.vertex_groups:
                    group = mesh_obj.vertex_groups[group_name]
                    group.add([current_vert_index], weight, 'REPLACE')
            restored_count += 1
    
    print(f"Successfully restored weights for {restored_count} vertices in {mesh_obj.name}")

# Merged from weights_io.py

"""
頂点ウェイトの保存・復元ユーティリティ
"""


def store_weights(target_obj, bone_groups_to_store):
    """頂点グループのウェイトを保存"""
    weights = {}
    for vert in target_obj.data.vertices:
        weights[vert.index] = {}
        for group in target_obj.vertex_groups:
            if group.name in bone_groups_to_store:
                try:
                    for g in vert.groups:
                        if g.group == group.index:
                            weights[vert.index][group.name] = g.weight
                            break
                except RuntimeError:
                    continue
    return weights


def restore_weights(target_obj, stored_weights):
    """保存したウェイトを復元"""
    for vert_idx, groups in stored_weights.items():
        for group_name, weight in groups.items():
            if group_name in target_obj.vertex_groups:
                target_obj.vertex_groups[group_name].add([vert_idx], weight, 'REPLACE')

# Merged from update_cloth_metadata.py

def update_cloth_metadata(metadata_dict: dict, output_path: str, vertex_index_mapping: dict) -> None:
    """
    ClothMetadataの頂点位置を更新し、指定されたパスに保存する
    
    Parameters:
        metadata_dict: 元のClothMetadataの辞書
        output_path: 保存先のパス
        vertex_index_mapping: Unity頂点インデックスからBlender頂点インデックスへのマッピング
    """
    # 各メッシュについて処理
    for cloth_data in metadata_dict.get("clothMetadata", []):
        mesh_name = cloth_data["meshName"]
        mesh_obj = bpy.data.objects.get(mesh_name)
        
        if not mesh_obj or mesh_obj.type != 'MESH':
            print(f"[Warning] Mesh {mesh_name} not found")
            continue
            
        # このメッシュのマッピング情報を取得
        mesh_mapping = vertex_index_mapping.get(mesh_name, {})
        if not mesh_mapping:
            print(f"[Warning] No vertex mappings found for {mesh_name}")
            continue
            
        # 評価済みメッシュを取得（モディファイア適用後の状態）
        depsgraph = bpy.context.evaluated_depsgraph_get()
        evaluated_obj = mesh_obj.evaluated_get(depsgraph)
        evaluated_mesh = evaluated_obj.data
        
        # vertexDataを更新
        for i, data in enumerate(cloth_data.get("vertexData", [])):
            # Unity頂点インデックスに対応するBlender頂点インデックスを取得
            blender_vert_idx = mesh_mapping.get(i)
            
            if blender_vert_idx is not None and blender_vert_idx < len(evaluated_mesh.vertices):
                # ワールド座標を取得
                world_pos = evaluated_obj.matrix_world @ evaluated_mesh.vertices[blender_vert_idx].co
                
                # Blender座標系からUnity座標系に変換
                data["position"]["x"] = -world_pos.x
                data["position"]["y"] = world_pos.z
                data["position"]["z"] = -world_pos.y
            else:
                print(f"[Warning] No mapping found for Unity vertex {i} in {mesh_name}")


    # 更新したデータを保存
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(metadata_dict, f, indent=4)
    except Exception:
        pass  # 保存失敗を無視
