import os
import sys

from mathutils import Vector
import bpy
import os
import sys


# Merged from get_armature_from_modifier.py

def get_armature_from_modifier(mesh_obj):
    """Armatureモディファイアからアーマチュアを取得"""
    for modifier in mesh_obj.modifiers:
        if modifier.type == 'ARMATURE':
            return modifier.object
    return None

# Merged from armature_modifier_utils.py


def set_armature_modifier_target_armature(obj, target_armature):
    """Armatureモディファイアのターゲットアーマチュアを設定"""
    for modifier in obj.modifiers:
        if modifier.type == 'ARMATURE':
            modifier.object = target_armature


def set_armature_modifier_visibility(obj, show_viewport, show_render):
    """Armatureモディファイアの表示を設定"""
    for modifier in obj.modifiers:
        if modifier.type == 'ARMATURE':
            modifier.show_viewport = show_viewport
            modifier.show_render = show_render


def store_armature_modifier_settings(obj):
    """Armatureモディファイアの設定を保存"""
    armature_settings = []
    for modifier in obj.modifiers:
        if modifier.type == 'ARMATURE':
            settings = {
                'name': modifier.name,
                'object': modifier.object,
                'vertex_group': modifier.vertex_group,
                'invert_vertex_group': modifier.invert_vertex_group,
                'use_vertex_groups': modifier.use_vertex_groups,
                'use_bone_envelopes': modifier.use_bone_envelopes,
                'use_deform_preserve_volume': modifier.use_deform_preserve_volume,
                'use_multi_modifier': modifier.use_multi_modifier,
                'show_viewport': modifier.show_viewport,
                'show_render': modifier.show_render,
            }
            armature_settings.append(settings)
    return armature_settings


def restore_armature_modifier(obj, settings):
    """Armatureモディファイアを復元"""
    for modifier_settings in settings:
        modifier = obj.modifiers.new(name=modifier_settings['name'], type='ARMATURE')
        modifier.object = modifier_settings['object']
        modifier.vertex_group = modifier_settings['vertex_group']
        modifier.invert_vertex_group = modifier_settings['invert_vertex_group']
        modifier.use_vertex_groups = modifier_settings['use_vertex_groups']
        modifier.use_bone_envelopes = modifier_settings['use_bone_envelopes']
        modifier.use_deform_preserve_volume = modifier_settings['use_deform_preserve_volume']
        modifier.use_multi_modifier = modifier_settings['use_multi_modifier']
        modifier.show_viewport = modifier_settings['show_viewport']
        modifier.show_render = modifier_settings['show_render']

# Merged from adjust_armature_hips_position.py

def adjust_armature_hips_position(armature_obj: bpy.types.Object, target_position: Vector, clothing_avatar_data: dict) -> None:
    """
    アーマチュアのHipsボーンを指定された位置に移動させる。
    子オブジェクトのワールド空間での位置を維持する。
    目標位置と現在位置が同じ場合は処理をスキップする。
    
    Parameters:
        armature_obj: アーマチュアオブジェクト
        target_position: 目標とするHipsボーンのワールド座標
        clothing_avatar_data: 衣装のアバターデータ
    """
    if not armature_obj or armature_obj.type != 'ARMATURE':
        return
        
    # Hipsボーンの名前を取得
    hips_bone_name = None
    for bone_map in clothing_avatar_data.get("humanoidBones", []):
        if bone_map["humanoidBoneName"] == "Hips":
            hips_bone_name = bone_map["boneName"]
            break
            
    if not hips_bone_name:
        print("[Warning] Hips bone not found in avatar data")
        return
        
    # 現在のHipsボーンのワールド座標を取得
    pose_bone = armature_obj.pose.bones.get(hips_bone_name)
    if not pose_bone:
        print(f"[Warning] Bone {hips_bone_name} not found in armature")
        return
        
    current_position = armature_obj.matrix_world @ pose_bone.head
    
    # 現在位置と目標位置の差を計算
    offset = target_position - current_position
    # 位置の差が十分小さい場合は処理をスキップ
    if offset.length < 0.0001:  # 0.1mm未満の差は無視
        return

    # 現在のアクティブオブジェクトとモードを保存
    current_active = bpy.context.active_object
    current_mode = current_active.mode if current_active else 'OBJECT'
    
    # オブジェクトモードに切り替え
    bpy.ops.object.mode_set(mode='OBJECT')
    
    # アーマチュアの子オブジェクトを取得
    children = []
    for child in bpy.data.objects:
        if child.parent == armature_obj:
            # 子オブジェクトの情報を保存
            children.append(child)
            
    # 親子関係を解除
    for child in children:
        # 他のオブジェクトの選択を解除
        bpy.ops.object.select_all(action='DESELECT')
        
        # 子オブジェクトを選択してアクティブに
        child.select_set(True)
        bpy.context.view_layer.objects.active = child
        
        # 親子関係を解除
        bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
    
    # アーマチュアを移動
    armature_obj.location += offset
    
    # 子オブジェクトの親子関係を復元
    for child in children:
        # 他のオブジェクトの選択を解除
        bpy.ops.object.select_all(action='DESELECT')
        
        # アーマチュアと子オブジェクトを選択
        armature_obj.select_set(True)
        child.select_set(True)
        bpy.context.view_layer.objects.active = armature_obj
        
        # 親子関係を設定
        bpy.ops.object.parent_set(type='OBJECT', keep_transform=True)
    
    # 元のアクティブオブジェクトと選択状態を復元
    bpy.ops.object.select_all(action='DESELECT')
    if current_active:
        current_active.select_set(True)
        bpy.context.view_layer.objects.active = current_active
        if current_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode=current_mode)
    
    # ビューを更新
    bpy.context.view_layer.update()

# Merged from apply_pose_as_rest.py

def apply_pose_as_rest(armature):
    # アクティブなオブジェクトを保存
    original_active = bpy.context.active_object
    
    # 指定されたアーマチュアを取得
    if not armature or armature.type != 'ARMATURE':
        print(f"[Error] {armature.name} is not a valid armature object")
        return
    
    # アーマチュアをアクティブに設定
    bpy.context.view_layer.objects.active = armature
    
    # 編集モードに入る
    bpy.ops.object.mode_set(mode='POSE')
    bpy.ops.pose.select_all(action='SELECT')
    
    # 現在のポーズをレストポーズとして適用
    bpy.ops.pose.armature_apply()
    
    # 元のモードに戻る
    bpy.ops.object.mode_set(mode='OBJECT')
    
    # 元のアクティブオブジェクトを復元
    bpy.context.view_layer.objects.active = original_active

# Merged from normalize_clothing_bone_names.py

def normalize_clothing_bone_names(clothing_armature: bpy.types.Object, clothing_avatar_data: dict, 
                                clothing_meshes: list) -> None:
    """
    Normalize bone names in clothing_avatar_data to match existing bones in clothing_armature.
    
    For each humanoidBone in clothing_avatar_data:
    1. Check if boneName exists in clothing_armature
    2. If not, convert boneName to lowercase alphabetic characters and find matching bone
    3. Update boneName in clothing_avatar_data if match found
    4. Update corresponding vertex group names in all clothing_meshes
    """
    import re
    
    # Get all bone names from clothing armature
    armature_bone_names = {bone.name for bone in clothing_armature.data.bones}
    # Store name changes for vertex group updates
    bone_name_changes = {}
    
    # Process each humanoid bone mapping
    for bone_map in clothing_avatar_data.get("humanoidBones", []):
        if "boneName" not in bone_map:
            continue
            
        original_bone_name = bone_map["boneName"]
        
        # Check if bone exists in armature
        if original_bone_name in armature_bone_names:
            continue
            
        # Extract alphabetic characters and convert to lowercase
        normalized_pattern = re.sub(r'[^a-zA-Z]', '', original_bone_name).lower()
        if not normalized_pattern:
            print(f"[Warning] No alphabetic characters found in bone name '{original_bone_name}'")
            continue
            
        
        # Find matching bone in armature
        matching_bone = None
        for armature_bone_name in armature_bone_names:
            armature_normalized = re.sub(r'[^a-zA-Z]', '', armature_bone_name).lower()
            if armature_normalized == normalized_pattern:
                matching_bone = armature_bone_name
                break
                
        if matching_bone:
            bone_name_changes[matching_bone] = original_bone_name
        else:
            print(f"[Warning] No matching bone found for '{original_bone_name}' (pattern: '{normalized_pattern}')")
    
    # Update vertex group names in all clothing meshes
    if bone_name_changes:
        for mesh_obj in clothing_meshes:
            if not mesh_obj or mesh_obj.type != 'MESH':
                continue
                
            for old_name, new_name in bone_name_changes.items():
                if old_name in mesh_obj.vertex_groups:
                    vertex_group = mesh_obj.vertex_groups[old_name]
                    vertex_group.name = new_name
        
        # Update bone names in clothing armature
        for old_name, new_name in bone_name_changes.items():
            if old_name in clothing_armature.data.bones:
                bone = clothing_armature.data.bones[old_name]
                bone.name = new_name
    
