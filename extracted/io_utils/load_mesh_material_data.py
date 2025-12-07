import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import json

import bpy
from algo_utils.search_utils import find_material_index_from_faces


def load_mesh_material_data(filepath):
    """
    メッシュマテリアルデータを読み込み、Blenderのメッシュにマテリアルを設定
    
    Args:
        filepath: メッシュマテリアルデータのJSONファイルパス
    """
    if not filepath or not os.path.exists(filepath):
        print("Warning: Mesh material data file not found or not specified")
        return
        
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
            print(f"Loaded mesh material data from: {filepath}")
            
            for mesh_data in data.get('meshMaterials', []):
                mesh_name = mesh_data['meshName']
                
                # Blenderでメッシュオブジェクトを検索
                mesh_obj = None
                for obj in bpy.data.objects:
                    if obj.type == 'MESH' and obj.name == mesh_name:
                        mesh_obj = obj
                        break
                
                if not mesh_obj:
                    print(f"Warning: Mesh {mesh_name} not found in Blender scene")
                    continue
                
                print(f"Processing mesh: {mesh_name}")
                
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
                        print(f"Created material: {material_name}")
                    
                    # 面から該当するマテリアルインデックスを特定し、そのスロットのマテリアルを入れ替え
                    material_index = find_material_index_from_faces(mesh_obj, faces_data)
                    if material_index is not None:
                        # メッシュにマテリアルスロットが不足している場合は追加
                        while len(mesh_obj.data.materials) <= material_index:
                            mesh_obj.data.materials.append(None)
                        
                        # 該当するマテリアルスロットを入れ替え
                        mesh_obj.data.materials[material_index] = material
                        print(f"Replaced material at index {material_index} with {material_name}")
                    else:
                        print(f"Warning: Could not find matching faces for material {material_name}")
                    
    except Exception as e:
        print(f"Error loading mesh material data: {e}")
