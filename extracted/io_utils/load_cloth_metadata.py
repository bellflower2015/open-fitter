import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import json

import bpy
from algo_utils.find_closest_vertices_brute_force import (
    find_closest_vertices_brute_force,
)
from math_utils.geometry_utils import calculate_vertices_world


def load_cloth_metadata(filepath):
    """
    変形後のワールド座標に基づいてClothメタデータをロード
    
    Returns:
        Tuple[dict, dict]: (メタデータのマッピング, Unity頂点インデックスからBlender頂点インデックスへのマッピング)
    """
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
                    print(f"Warning: Mesh {mesh_name} not found")
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
                print(f"Original vertex count: {len(metadata['vertexData'])}")
                print(f"Original unity position count: {len(unity_positions)}")
                print(f"Mapped vertex count: {len(vertex_max_distances)}")

                # マッピングできなかった頂点を特定
                mapped_indices = set(int(idx) for idx in vertex_max_distances.keys())
                unmapped_indices = set(range(len(vertices_world))) - mapped_indices
                
                if unmapped_indices:
                    print(f"Warning: Could not map {len(unmapped_indices)} vertices")
                    
                    # デバッグ用の頂点グループを作成
                    debug_group_name = "DEBUG_UnmappedVertices"
                    if debug_group_name in mesh_obj.vertex_groups:
                        mesh_obj.vertex_groups.remove(mesh_obj.vertex_groups[debug_group_name])
                    debug_group = mesh_obj.vertex_groups.new(name=debug_group_name)
                    
                    # マッピングできなかった頂点をグループに追加
                    for idx in unmapped_indices:
                        debug_group.add([idx], 1.0, 'REPLACE')
                    
                    print(f"Created vertex group '{debug_group_name}' with {len(unmapped_indices)} vertices")
                    
                    # デバッグ情報
                    print(f"First 5 unmapped vertices world positions:")
                    for idx in list(unmapped_indices)[:5]:
                        print(f"Vertex {idx}: {vertices_world[idx]}")
            
            return metadata_by_mesh, vertex_index_mapping
            
    except Exception as e:
        print(f"Failed to load cloth metadata: {e}")
        import traceback
        traceback.print_exc()
        return {}, {}
