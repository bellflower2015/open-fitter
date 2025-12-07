"""Humanoid bone replacement for clothing avatars.

This module provides the main orchestration for replacing humanoid bones
in a clothing armature with bones from a base armature.
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from typing import Optional

import bmesh
import bpy
from add_pose_from_json import add_pose_from_json
from algo_utils.search_utils import (
    find_humanoid_parent_in_hierarchy,
)
from algo_utils.bone_group_utils import (
    get_humanoid_and_auxiliary_bone_groups_with_intermediate,
)
from armature_bone_replacer import (
    apply_sub_humanoid_bone_substitution,
    collect_children_to_update,
    create_new_bones,
    finish_edit_mode,
    parent_original_bones_to_new,
    process_bones_to_preserve_or_delete,
    set_new_bone_parents,
    store_base_bone_parents,
    update_children_parents,
)
from blender_utils.apply_pose_as_rest import apply_pose_as_rest
from blender_utils.inverse_bone_deform_all_vertices import (
    inverse_bone_deform_all_vertices,
)
from bone_mapping_builder import BoneMappings, build_bone_mappings
from mathutils.bvhtree import BVHTree
from parent_bone_finder import find_parent_bones


class _ReplaceHumanoidBonesContext:
    """State holder for humanoid bone replacement steps."""

    def __init__(
        self,
        base_armature: bpy.types.Object,
        clothing_armature: bpy.types.Object,
        base_avatar_data: dict,
        clothing_avatar_data: dict,
        preserve_humanoid_bones: bool,
        base_pose_filepath: Optional[str],
        clothing_meshes: list,
        process_upper_chest: bool,
    ):
        # Input parameters
        self.base_armature = base_armature
        self.clothing_armature = clothing_armature
        self.base_avatar_data = base_avatar_data
        self.clothing_avatar_data = clothing_avatar_data
        self.preserve_humanoid_bones = preserve_humanoid_bones
        self.base_pose_filepath = base_pose_filepath
        self.clothing_meshes = clothing_meshes
        self.process_upper_chest = process_upper_chest

        # Original state
        self.original_active = bpy.context.active_object
        self.original_mode = self.original_active.mode if self.original_active else 'OBJECT'

        # Bone mappings (populated by build_bone_mappings)
        self.mappings: Optional[BoneMappings] = None

        # Derived data
        self.base_bones: set[str] = set()

        # BVH data
        self.base_mesh: Optional[bpy.types.Object] = None
        self.bmesh_data: Optional[bmesh.types.BMesh] = None
        self.bvh: Optional[BVHTree] = None
        self.base_group_index_to_name: dict[int, str] = {}

        # Modifier backup
        self.armature_modifiers: list[dict] = []
        self.clothing_obj_list: list[bpy.types.Object] = []

        # Intermediate data for bone replacement
        self.clothing_bone_data: dict[str, dict] = {}
        self.parent_bones: dict[str, str] = {}

    # =========================================================================
    # Step 1: Create bone mappings
    # =========================================================================
    def create_bone_mappings(self):
        """Create all bone name mappings from avatar data."""
        self.mappings = build_bone_mappings(
            self.base_avatar_data,
            self.clothing_avatar_data,
            self.preserve_humanoid_bones,
        )

    def get_base_bones(self):
        """Get humanoid and auxiliary bone groups from base armature."""
        self.base_bones = get_humanoid_and_auxiliary_bone_groups_with_intermediate(
            self.base_armature, self.base_avatar_data
        )

    # =========================================================================
    # Step 2: Build BVH tree
    # =========================================================================
    def build_bvh_tree(self):
        """Build BVH tree from base mesh for spatial queries."""
        self.base_mesh = bpy.data.objects.get("Body.BaseAvatar")
        if not self.base_mesh:
            raise Exception("Body.BaseAvatar not found")

        self.bmesh_data = bmesh.new()
        self.bmesh_data.from_mesh(self.base_mesh.data)
        self.bmesh_data.faces.ensure_lookup_table()
        self.bmesh_data.transform(self.base_mesh.matrix_world)
        self.bvh = BVHTree.FromBMesh(self.bmesh_data)

        self.base_group_index_to_name = {
            group.index: group.name for group in self.base_mesh.vertex_groups
        }

    def free_bvh_resources(self):
        """Free BVH and bmesh resources."""
        if self.bmesh_data:
            self.bmesh_data.free()
            self.bmesh_data = None

    # =========================================================================
    # Step 3: Backup armature modifiers
    # =========================================================================
    def backup_armature_modifiers(self):
        """Backup and temporarily remove armature modifiers."""
        for obj in bpy.data.objects:
            if obj.type == 'MESH':
                for modifier in obj.modifiers[:]:
                    if modifier.type == 'ARMATURE' and modifier.object == self.clothing_armature:
                        mod_settings = {
                            'object': obj,
                            'name': modifier.name,
                            'target': modifier.object,
                            'vertex_group': modifier.vertex_group,
                            'invert_vertex_group': modifier.invert_vertex_group,
                            'use_vertex_groups': modifier.use_vertex_groups,
                            'use_bone_envelopes': modifier.use_bone_envelopes,
                            'use_deform_preserve_volume': modifier.use_deform_preserve_volume,
                        }
                        self.armature_modifiers.append(mod_settings)
                        obj.modifiers.remove(modifier)
                        self.clothing_obj_list.append(obj)

    def restore_armature_modifiers(self):
        """Restore armature modifiers from backup."""
        for mod_settings in self.armature_modifiers:
            obj = mod_settings['object']
            modifier = obj.modifiers.new(name=mod_settings['name'], type='ARMATURE')
            modifier.object = mod_settings['target']
            modifier.vertex_group = mod_settings['vertex_group']
            modifier.invert_vertex_group = mod_settings['invert_vertex_group']
            modifier.use_vertex_groups = mod_settings['use_vertex_groups']
            modifier.use_bone_envelopes = mod_settings['use_bone_envelopes']
            modifier.use_deform_preserve_volume = mod_settings['use_deform_preserve_volume']

    # =========================================================================
    # Step 4: Apply initial pose
    # =========================================================================
    def apply_initial_pose(self):
        """Apply initial pose to clothing armature if base_pose_filepath is provided."""
        if self.base_pose_filepath:
            print(f"Applying clothing base pose from {self.base_pose_filepath}")
            add_pose_from_json(
                self.clothing_armature, self.base_pose_filepath, self.clothing_avatar_data, invert=True
            )
            apply_pose_as_rest(self.clothing_armature)

    # =========================================================================
    # Step 5: Collect clothing bone data
    # =========================================================================
    def collect_clothing_bone_data(self):
        """Collect clothing bone positions and their candidate parent bones."""
        clothing_matrix_world = self.clothing_armature.matrix_world

        for bone in self.clothing_armature.pose.bones:
            if bone.parent and bone.parent.name in self.mappings.bones_to_replace and bone.name not in self.mappings.bones_to_replace:
                head_pos = clothing_matrix_world @ bone.head

                # Get humanoid name of parent bone
                parent_humanoid = self._get_parent_humanoid_name(bone.parent.name)

                # If parent_humanoid is not in base_humanoid_map, find valid parent in hierarchy
                if parent_humanoid and parent_humanoid not in self.mappings.base_humanoid_map:
                    parent_humanoid = find_humanoid_parent_in_hierarchy(
                        bone.parent.name, self.clothing_avatar_data, self.base_avatar_data
                    )

                if parent_humanoid and parent_humanoid in self.mappings.base_humanoid_map:
                    candidate_bones, sub_parent_humanoid = self._get_candidate_bones(parent_humanoid)

                    self.clothing_bone_data[bone.name] = {
                        'head_pos': head_pos,
                        'candidate_bones': candidate_bones,
                        'parent_humanoid': self.mappings.base_humanoid_map[parent_humanoid],
                        'sub_parent_humanoid': sub_parent_humanoid,
                    }

    def _get_parent_humanoid_name(self, bone_name: str) -> Optional[str]:
        """Get humanoid name for a bone."""
        if bone_name in self.mappings.clothing_humanoid_map:
            return self.mappings.clothing_humanoid_map[bone_name]
        elif bone_name in self.mappings.aux_to_humanoid:
            return self.mappings.aux_to_humanoid[bone_name]
        return None

    def _get_candidate_bones(self, parent_humanoid: str) -> tuple[set[str], Optional[str]]:
        """Get candidate bones for parent matching."""
        candidate_bones = {self.mappings.base_humanoid_map[parent_humanoid]}
        if parent_humanoid in self.mappings.humanoid_to_aux_base:
            candidate_bones.update(self.mappings.humanoid_to_aux_base[parent_humanoid])

        sub_parent_humanoid = None
        if parent_humanoid == 'Chest' and 'UpperChest' in self.mappings.base_humanoid_map and self.process_upper_chest:
            sub_parent_humanoid = self.mappings.base_humanoid_map['UpperChest']
            candidate_bones.add(sub_parent_humanoid)
            if 'UpperChest' in self.mappings.humanoid_to_aux_base:
                candidate_bones.update(self.mappings.humanoid_to_aux_base['UpperChest'])

        return candidate_bones, sub_parent_humanoid

    # =========================================================================
    # Step 6: Find parent bones (uses parent_bone_finder module)
    # =========================================================================
    def find_parent_bones_step(self):
        """Find parent bones for each clothing bone using weight-based scoring."""
        self.parent_bones = find_parent_bones(
            self.clothing_bone_data,
            self.clothing_meshes,
            self.base_armature,
            self.clothing_armature,
            self.bvh,
            self.bmesh_data,
            self.base_mesh,
            self.base_group_index_to_name,
        )

    # =========================================================================
    # Step 8: Apply final pose
    # =========================================================================
    def apply_final_pose(self):
        """Apply final pose transformations if base_pose_filepath is provided."""
        if self.base_pose_filepath:
            print(f"Applying base pose from {self.base_pose_filepath}")
            add_pose_from_json(
                self.clothing_armature, self.base_pose_filepath, self.base_avatar_data, invert=False
            )
            for obj in self.clothing_obj_list:
                inverse_bone_deform_all_vertices(self.clothing_armature, obj)
            add_pose_from_json(
                self.clothing_armature, self.base_pose_filepath, self.base_avatar_data, invert=True
            )
            apply_pose_as_rest(self.clothing_armature)

    # =========================================================================
    # Step 9: Restore original state
    # =========================================================================
    def restore_original_state(self):
        """Restore original active object and mode."""
        bpy.context.view_layer.objects.active = self.original_active
        if self.original_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode=self.original_mode)


def replace_humanoid_bones(
    base_armature: bpy.types.Object,
    clothing_armature: bpy.types.Object,
    base_avatar_data: dict,
    clothing_avatar_data: dict,
    preserve_humanoid_bones: bool,
    base_pose_filepath: Optional[str],
    clothing_meshes: list,
    process_upper_chest: bool,
) -> None:
    """Replace humanoid bones in clothing armature with bones from base armature."""

    ctx = _ReplaceHumanoidBonesContext(
        base_armature,
        clothing_armature,
        base_avatar_data,
        clothing_avatar_data,
        preserve_humanoid_bones,
        base_pose_filepath,
        clothing_meshes,
        process_upper_chest,
    )

    # Step 1: Create bone mappings
    ctx.create_bone_mappings()
    ctx.get_base_bones()

    # Step 2: Build BVH tree for spatial queries
    ctx.build_bvh_tree()

    try:
        # Step 3: Backup and remove armature modifiers
        ctx.backup_armature_modifiers()

        # Step 4: Apply initial pose
        ctx.apply_initial_pose()

        # Step 5: Collect clothing bone data
        ctx.collect_clothing_bone_data()

        # Step 6: Find parent bones using weight-based scoring
        ctx.find_parent_bones_step()

        # Step 7: Replace bones in armature
        children_to_update = collect_children_to_update(
            ctx.clothing_armature, ctx.mappings.bones_to_replace
        )
        base_bone_parents = store_base_bone_parents(ctx.base_armature, ctx.base_bones)
        original_bone_data = process_bones_to_preserve_or_delete(
            ctx.clothing_armature,
            ctx.mappings.bones_to_replace,
            ctx.mappings.humanoid_bones_to_preserve,
            ctx.mappings.clothing_bones_to_humanoid,
        )
        new_bones = create_new_bones(ctx.clothing_armature, ctx.base_armature, ctx.base_bones)
        set_new_bone_parents(new_bones, base_bone_parents)
        parent_original_bones_to_new(
            ctx.clothing_armature,
            original_bone_data,
            new_bones,
            ctx.mappings.base_bone_to_humanoid,
            ctx.clothing_avatar_data,
            ctx.base_avatar_data,
        )
        apply_sub_humanoid_bone_substitution(
            ctx.parent_bones, ctx.base_avatar_data, ctx.mappings.base_bone_to_humanoid
        )
        update_children_parents(ctx.clothing_armature, children_to_update, ctx.parent_bones)
        finish_edit_mode()

        # Step 8: Apply final pose
        ctx.apply_final_pose()

        # Step 9: Restore armature modifiers
        ctx.restore_armature_modifiers()

    finally:
        # Cleanup: Free BVH resources
        ctx.free_bvh_resources()

        # Restore original state
        ctx.restore_original_state()
