import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from misc_utils.globals import _mesh_cache
import bmesh
import bpy
import os
import sys

# Merged from get_evaluated_mesh.py

def get_evaluated_mesh(obj):
    """モディファイア適用後のメッシュを取得"""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated_obj = obj.evaluated_get(depsgraph)
    evaluated_mesh = evaluated_obj.data
    
    # BMeshを作成して評価済みメッシュの情報を取得
    bm = bmesh.new()
    bm.from_mesh(evaluated_mesh)
    bm.transform(obj.matrix_world)
    return bm

# Merged from clear_mesh_cache.py

def clear_mesh_cache():
    """
    メッシュキャッシュをクリアします
    """
    global _mesh_cache
    
    # BMeshオブジェクトを解放
    for cache_data in _mesh_cache.values():
        if 'bmesh' in cache_data and cache_data['bmesh']:
            cache_data['bmesh'].free()
    
    _mesh_cache.clear()
    print("メッシュキャッシュをクリアしました")

# Merged from triangulate_mesh.py

def triangulate_mesh(obj: bpy.types.Object) -> None:
    """
    現在の3DView上でのレンダリングにおける三角面への分割をそのまま利用して、
    メッシュのすべての面を三角面に変換する。
    
    Args:
        obj: 三角分割するメッシュオブジェクト
    """
    if obj is None or obj.type != 'MESH':
        return
    
    # 元のアクティブオブジェクトを保存
    original_active = bpy.context.view_layer.objects.active
    
    try:
        # オブジェクトをアクティブに設定
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        
        # エディットモードに切り替え
        bpy.ops.object.mode_set(mode='EDIT')
        
        # 全ての面を選択
        bpy.ops.mesh.select_all(action='SELECT')
        
        # 三角分割を実行（bmeshの三角分割を使用）
        bpy.ops.mesh.quads_convert_to_tris(quad_method='FIXED', ngon_method='BEAUTY')
        
        # オブジェクトモードに戻る
        bpy.ops.object.mode_set(mode='OBJECT')
        
        print(f"Triangulated mesh: {obj.name}")
        
    except Exception as e:
        print(f"Error triangulating mesh {obj.name}: {e}")
        # エラーが発生した場合もオブジェクトモードに戻る
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except:
            pass
    
    finally:
        # 元のアクティブオブジェクトを復元
        if original_active:
            bpy.context.view_layer.objects.active = original_active
        obj.select_set(False)

# Merged from apply_all_transforms.py

def apply_all_transforms():
    """Apply transforms to all objects while maintaining world space positions"""
    
    bpy.ops.object.mode_set(mode='OBJECT')
    
    # 選択状態を保存
    original_selection = {obj: obj.select_get() for obj in bpy.data.objects}
    original_active = bpy.context.view_layer.objects.active
    
    # すべてのオブジェクトを取得し、親子関係の深さでソート
    def get_object_depth(obj):
        depth = 0
        parent = obj.parent
        while parent:
            depth += 1
            parent = parent.parent
        return depth
    
    # 深い階層から順番に処理するためにソート
    all_objects = sorted(bpy.data.objects, key=get_object_depth, reverse=True)
    
    # 親子関係情報を保存するリスト
    parent_info_list = []
    
    # 第1段階: すべてのオブジェクトで親子関係を解除してTransformを適用
    for obj in all_objects:
        if obj.type not in {'MESH', 'EMPTY', 'ARMATURE', 'CURVE', 'SURFACE', 'FONT'}:
            continue
        
        # すべての選択を解除
        bpy.ops.object.select_all(action='DESELECT')
        
        # 現在のオブジェクトを選択してアクティブに
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        
        # 親子関係情報を保存
        parent = obj.parent
        parent_type = obj.parent_type
        parent_bone = obj.parent_bone if parent_type == 'BONE' else None
        
        if parent:
            parent_info_list.append({
                'obj': obj,
                'parent': parent,
                'parent_type': parent_type,
                'parent_bone': parent_bone
            })
        
        # 親子関係を一時的に解除（位置は保持）
        if parent:
            bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
        
        # Armatureオブジェクトまたは Armature モディファイアを持つMeshオブジェクトの場合
        has_armature = obj.type == 'ARMATURE' or \
                      (obj.type == 'MESH' and any(mod.type == 'ARMATURE' for mod in obj.modifiers))
        
        if has_armature:
            # すべての Transform を適用
            bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        else:
            # スケールのみ適用
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    
    # 第2段階: すべての親子関係をまとめて復元
    for parent_info in parent_info_list:
        obj = parent_info['obj']
        parent = parent_info['parent']
        parent_type = parent_info['parent_type']
        parent_bone = parent_info['parent_bone']
        
        # すべての選択を解除
        bpy.ops.object.select_all(action='DESELECT')
        
        if parent_type == 'BONE' and parent_bone:
            # ボーン親だった場合
            obj.select_set(True)
            bpy.context.view_layer.objects.active = parent
            parent.select_set(True)
            
            # ポーズモードに切り替えてボーンをアクティブに設定
            bpy.ops.object.mode_set(mode='POSE')
            parent.data.bones.active = parent.data.bones[parent_bone]
            
            # オブジェクトモードに戻る
            bpy.ops.object.mode_set(mode='OBJECT')
            
            # ボーンペアレントを設定
            bpy.ops.object.parent_set(type='BONE', keep_transform=True)
            print(f"Restored bone parent '{parent_bone}' for object '{obj.name}'")
        else:
            # オブジェクト親だった場合
            obj.select_set(True)
            parent.select_set(True)
            bpy.context.view_layer.objects.active = parent
            bpy.ops.object.parent_set(type='OBJECT', keep_transform=True)
    
    # 元の選択状態を復元
    for obj, was_selected in original_selection.items():
        obj.select_set(was_selected)
    bpy.context.view_layer.objects.active = original_active

# Merged from apply_modifiers_keep_shapekeys_with_temp.py

def apply_modifiers(obj):
    """モディファイアを適用"""
    bpy.context.view_layer.objects.active = obj
    for modifier in obj.modifiers[:]:  # スライスを使用してリストのコピーを作成
        try:
            bpy.ops.object.modifier_apply(modifier=modifier.name)
        except Exception as e:
            print(f"Failed to apply modifier {modifier.name}: {e}")


def apply_all_shapekeys(obj):
    """オブジェクトの全シェイプキーを適用する"""
    if not obj.data.shape_keys:
        return
    
    # 基底シェイプキーは常にインデックス0
    if obj.active_shape_key_index == 0 and len(obj.data.shape_keys.key_blocks) > 1:
        obj.active_shape_key_index = 1
    else:
        obj.active_shape_key_index = 0

    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.shape_key_remove(all=True, apply_mix=True)


def apply_modifiers_keep_shapekeys_with_temp(obj):
    """一時オブジェクトを使用してシェイプキーを維持しながらモディファイアを適用する"""
    if obj.type != 'MESH':
        return
    
    if not obj.data.shape_keys:
        # シェイプキーがない場合は通常のモディファイア適用
        bpy.context.view_layer.objects.active = obj
        for modifier in obj.modifiers:
            try:
                bpy.ops.object.modifier_apply(modifier=modifier.name)
            except Exception as e:
                print(f"Failed to apply modifier {modifier.name}: {e}")
        return

    # グローバルカウンタの初期化（存在しない場合）
    if not hasattr(apply_modifiers_keep_shapekeys_with_temp, 'counter'):
        apply_modifiers_keep_shapekeys_with_temp.counter = 0

    shape_keys = obj.data.shape_keys.key_blocks
    temp_objects = []
    shape_key_names = []  # 元のシェイプキー名を保存するリスト
    
    # 各シェイプキーに対して一時オブジェクトを作成
    for i, shape_key in enumerate(shape_keys):
        if i == 0:  # Basis は飛ばす
            continue
        
        # すべてのオブジェクトの選択を解除
        bpy.ops.object.select_all(action='DESELECT')
        # オブジェクトを複製
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.duplicate(linked=False)
        temp_obj = bpy.context.active_object

        temp_obj.name = f"t{apply_modifiers_keep_shapekeys_with_temp.counter}"
        apply_modifiers_keep_shapekeys_with_temp.counter += 1

        temp_objects.append(temp_obj)
        shape_key_names.append(shape_key.name)  # 元の名前を保存
        
        # 他のシェイプキーの値を0に、対象のシェイプキーの値を1に設定
        for sk in temp_obj.data.shape_keys.key_blocks:
            if sk.name == shape_key.name:
                sk.value = 1.0
            else:
                sk.value = 0.0
        
        # シェイプキーを適用
        apply_all_shapekeys(temp_obj)
        
        # Armature以外のモディファイアを適用
        apply_modifiers(temp_obj)

    # 元のオブジェクトの処理
    bpy.context.view_layer.objects.active = obj
    # まず全てのシェイプキーの値を0に設定
    for sk in obj.data.shape_keys.key_blocks:
        sk.value = 0.0
    # シェイプキーを適用
    apply_all_shapekeys(obj)
    # モディファイアを適用
    apply_modifiers(obj)

    # 一時オブジェクトの形状を元のオブジェクトのシェイプキーとして追加
    obj.shape_key_add(name="Basis")
    for temp_obj, original_name in zip(temp_objects, shape_key_names):
        # シェイプキーを追加（元の名前を使用）
        shape_key = obj.shape_key_add(name=original_name)
        shape_key.interpolation = 'KEY_LINEAR'
        if shape_key.name == "SymmetricDeformed":
            shape_key.value = 1.0
        
        # 頂点座標を設定
        for i, vert in enumerate(temp_obj.data.vertices):
            shape_key.data[i].co = vert.co.copy()
        
        # 一時オブジェクトを削除
        bpy.data.objects.remove(temp_obj, do_unlink=True)

# Merged from reset_utils.py

"""
シェイプキー・ボーンウェイトのリセットユーティリティ
"""


def reset_shape_keys(obj):
    """全シェイプキーの値を0にリセット（Basis以外）"""
    if obj.data.shape_keys is not None:
        for kb in obj.data.shape_keys.key_blocks:
            if kb.name != "Basis":
                kb.value = 0.0


def reset_bone_weights(target_obj, bone_groups):
    """指定された頂点グループのウェイトを0に設定"""
    for vert in target_obj.data.vertices:
        for group in target_obj.vertex_groups:
            if group.name in bone_groups:
                try:
                    group.add([vert.index], 0, 'REPLACE')
                except RuntimeError:
                    continue

# Merged from base_object_utils.py

# Merged from rename_base_objects.py

def rename_base_objects(mesh_obj: bpy.types.Object, armature_obj: bpy.types.Object) -> tuple:
    """Rename base mesh and armature to specific names."""
    # Store original names for reference
    original_mesh_name = mesh_obj.name
    original_armature_name = armature_obj.name
    
    # Rename mesh to Body.BaseAvatar
    mesh_obj.name = "Body.BaseAvatar"
    mesh_obj.data.name = "Body.BaseAvatar_Mesh"
    
    # Rename armature to Armature.BaseAvatar
    armature_obj.name = "Armature.BaseAvatar"
    armature_obj.data.name = "Armature.BaseAvatar_Data"
    
    print(f"Renamed base objects: {original_mesh_name} -> {mesh_obj.name}, {original_armature_name} -> {armature_obj.name}")
    return mesh_obj, armature_obj

# Merged from cleanup_base_objects.py

def cleanup_base_objects(mesh_name: str) -> tuple:
    """Delete all objects except the specified mesh and its armature."""
    
    original_mode = bpy.context.object.mode
    bpy.ops.object.mode_set(mode='OBJECT')
    
    # Find the mesh and its armature
    target_mesh = None
    target_armature = None
    
    for obj in bpy.data.objects:
        if obj.type == 'MESH' and obj.name == mesh_name:
            target_mesh = obj
            # Find associated armature through modifiers
            for modifier in obj.modifiers:
                if modifier.type == 'ARMATURE':
                    target_armature = modifier.object
                    break
    
    if not target_mesh:
        raise Exception(f"Mesh '{mesh_name}' not found")
    
    if target_armature and target_armature.parent:
        original_active = bpy.context.view_layer.objects.active
        bpy.context.view_layer.objects.active = target_armature
        bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
        bpy.context.view_layer.objects.active = original_active
    
    # Delete all other objects
    for obj in bpy.data.objects[:]:  # Create a copy of the list to avoid modification during iteration
        if obj != target_mesh and obj != target_armature:
            bpy.data.objects.remove(obj, do_unlink=True)
            
    #bpy.ops.object.mode_set(mode=original_mode)
    
    # Rename objects to specified names
    return rename_base_objects(target_mesh, target_armature)