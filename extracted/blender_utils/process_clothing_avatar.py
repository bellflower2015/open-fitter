import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import json

import bpy
from blender_utils.armature_utils import adjust_armature_hips_position


class _ClothingAvatarContext:
    """State holder for clothing avatar import steps."""

    def __init__(self, input_fbx, clothing_avatar_data_path, hips_position, target_meshes, mesh_renderers):
        self.input_fbx = input_fbx
        self.clothing_avatar_data_path = clothing_avatar_data_path
        self.hips_position = hips_position
        self.target_meshes = target_meshes
        self.mesh_renderers = mesh_renderers
        self.original_active = bpy.context.view_layer.objects.active
        self.clothing_avatar_data = None
        self.clothing_armature = None
        self.clothing_meshes = []

    def import_fbx(self):
        bpy.ops.import_scene.fbx(filepath=self.input_fbx, use_anim=False)

    def remove_inactive_objects(self):
        """非アクティブなオブジェクトとそのすべての子を削除する"""
        objects_to_remove = []

        def is_object_inactive(obj):
            # hide_viewport または hide_render が True の場合、非アクティブと判定
            return obj.hide_viewport or obj.hide_render or obj.hide_get()

        def collect_children_recursive(obj, collected_list):
            for child in obj.children:
                collected_list.append(child)
                collect_children_recursive(child, collected_list)

        for obj in bpy.data.objects:
            if is_object_inactive(obj) and obj not in objects_to_remove:
                objects_to_remove.append(obj)
                collect_children_recursive(obj, objects_to_remove)

        objects_to_remove = list(set(objects_to_remove))

        for obj in objects_to_remove:
            obj_name = obj.name
            try:
                bpy.data.objects.remove(obj, do_unlink=True)
                print(f"Removed inactive object: {obj_name}")
            except Exception as e:
                print(f"Failed to remove object {obj_name}: {e}")

    def load_avatar_data(self):
        print(f"Loading clothing avatar data from {self.clothing_avatar_data_path}")
        with open(self.clothing_avatar_data_path, 'r', encoding='utf-8') as f:
            self.clothing_avatar_data = json.load(f)

    def find_clothing_armature(self):
        for obj in bpy.data.objects:
            if obj.type == 'ARMATURE' and obj.name != "Armature.BaseAvatar":
                self.clothing_armature = obj
                break
        if not self.clothing_armature:
            raise Exception("Clothing armature not found")

    def collect_clothing_meshes(self):
        meshes = []
        for obj in bpy.data.objects:
            if obj.type == 'MESH' and obj.name not in (
                "Body.BaseAvatar",
                "Body.BaseAvatar.RightOnly",
                "Body.BaseAvatar.LeftOnly",
            ):
                has_armature = any(modifier.type == 'ARMATURE' for modifier in obj.modifiers)
                if has_armature and len(obj.data.vertices) > 0:
                    meshes.append(obj)
                elif has_armature and len(obj.data.vertices) == 0:
                    print(f"Skipping mesh '{obj.name}': vertex count is 0")
        self.clothing_meshes = meshes

    def filter_target_meshes(self):
        if not self.target_meshes:
            return
        target_mesh_list = [name for name in self.target_meshes.split(';')]
        print(f"Target mesh list: {target_mesh_list}")
        filtered_meshes = []
        for obj in self.clothing_meshes:
            if obj.name in target_mesh_list:
                filtered_meshes.append(obj)
            else:
                obj_name = obj.name
                bpy.data.objects.remove(obj, do_unlink=True)
                print(f"Removed non-target mesh: {obj_name}")
        if not filtered_meshes:
            raise Exception(f"No target meshes found. Specified: {self.target_meshes}")
        self.clothing_meshes = filtered_meshes

    def set_hips_position(self):
        if self.hips_position:
            adjust_armature_hips_position(self.clothing_armature, self.hips_position, self.clothing_avatar_data)

    def _set_parent_bone(self, mesh_obj, parent_name):
        bpy.ops.object.select_all(action='DESELECT')
        mesh_obj.select_set(True)
        bpy.context.view_layer.objects.active = self.clothing_armature
        self.clothing_armature.select_set(True)
        bpy.ops.object.mode_set(mode='POSE')
        self.clothing_armature.data.bones.active = self.clothing_armature.data.bones[parent_name]
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.parent_set(type='BONE', keep_transform=True)
        print(f"Set parent bone '{parent_name}' for mesh '{mesh_obj.name}' (world transform preserved)")
        bpy.ops.object.select_all(action='DESELECT')

    def process_mesh_renderers(self):
        if not self.mesh_renderers:
            return
        print(f"Processing mesh renderers: {self.mesh_renderers}")
        for mesh_name, parent_name in self.mesh_renderers.items():
            mesh_obj = next((obj for obj in bpy.data.objects if obj.type == 'MESH' and obj.name == mesh_name), None)
            if not mesh_obj:
                print(f"Warning: Mesh object '{mesh_name}' not found")
                continue

            has_armature = any(modifier.type == 'ARMATURE' for modifier in mesh_obj.modifiers)
            current_parent_name = mesh_obj.parent.name if mesh_obj.parent else None

            if has_armature or current_parent_name == parent_name:
                if has_armature:
                    print(f"Skipping mesh '{mesh_name}': already has Armature modifier")
                else:
                    print(f"Skipping mesh '{mesh_name}': parent already matches ('{current_parent_name}')")
                continue

            bone_found = parent_name in self.clothing_armature.data.bones
            if bone_found:
                self._set_parent_bone(mesh_obj, parent_name)
            else:
                print(f"Warning: Bone '{parent_name}' not found in clothing_armature for mesh '{mesh_name}'")

    def restore_active(self):
        bpy.context.view_layer.objects.active = self.original_active


def process_clothing_avatar(input_fbx, clothing_avatar_data_path, hips_position=None, target_meshes=None, mesh_renderers=None):
    """Process clothing avatar."""

    ctx = _ClothingAvatarContext(input_fbx, clothing_avatar_data_path, hips_position, target_meshes, mesh_renderers)

    ctx.import_fbx()
    ctx.remove_inactive_objects()
    ctx.load_avatar_data()
    ctx.find_clothing_armature()
    ctx.collect_clothing_meshes()
    ctx.filter_target_meshes()
    ctx.set_hips_position()
    ctx.process_mesh_renderers()
    ctx.restore_active()

    return ctx.clothing_meshes, ctx.clothing_armature, ctx.clothing_avatar_data
