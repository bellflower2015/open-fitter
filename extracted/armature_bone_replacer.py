"""Armature bone replacer for humanoid bone replacement.

This module provides functions for replacing bones in the armature,
including bone creation, parent relationship management, and hierarchy updates.
"""

import os
import sys
from typing import Optional

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import bpy
from algo_utils.search_utils import (
    find_humanoid_parent_in_hierarchy,
)
from math_utils.geometry_utils import copy_bone_transform


def collect_children_to_update(
    clothing_armature: bpy.types.Object,
    bones_to_replace: set[str],
) -> list[str]:
    """Collect children bones that need parent updates.

    Args:
        clothing_armature: Clothing armature object.
        bones_to_replace: Set of bones to be replaced.

    Returns:
        List of bone names that need parent updates.
    """
    bpy.context.view_layer.objects.active = clothing_armature
    bpy.ops.object.mode_set(mode='EDIT')
    clothing_edit_bones = clothing_armature.data.edit_bones

    children_to_update = []
    for bone in clothing_edit_bones:
        if bone.parent and bone.parent.name in bones_to_replace and bone.name not in bones_to_replace:
            children_to_update.append(bone.name)

    return children_to_update


def store_base_bone_parents(
    base_armature: bpy.types.Object,
    base_bones: set[str],
) -> dict[str, Optional[str]]:
    """Store parent relationships from base armature.

    Args:
        base_armature: Base armature object.
        base_bones: Set of base bone names.

    Returns:
        Dictionary mapping bone names to their parent names.
    """
    bpy.context.view_layer.objects.active = base_armature
    bpy.ops.object.mode_set(mode='EDIT')

    base_bone_parents = {}
    for bone in base_armature.data.edit_bones:
        if bone.name in base_bones:
            base_bone_parents[bone.name] = (
                bone.parent.name if bone.parent and bone.parent.name in base_bones else None
            )

    print(base_bone_parents)
    return base_bone_parents


def process_bones_to_preserve_or_delete(
    clothing_armature: bpy.types.Object,
    bones_to_replace: set[str],
    humanoid_bones_to_preserve: set[str],
    clothing_bones_to_humanoid: dict[str, str],
) -> dict[str, dict]:
    """Process bones: preserve humanoid bones or delete others.

    Args:
        clothing_armature: Clothing armature object.
        bones_to_replace: Set of bones to be replaced.
        humanoid_bones_to_preserve: Set of humanoid bones to preserve.
        clothing_bones_to_humanoid: Mapping from bone names to humanoid names.

    Returns:
        Dictionary containing original bone data for preserved bones.
    """
    bpy.context.view_layer.objects.active = clothing_armature
    bpy.ops.object.mode_set(mode='EDIT')
    clothing_edit_bones = clothing_armature.data.edit_bones

    original_bone_data = {}
    for bone_name in bones_to_replace:
        if bone_name in clothing_edit_bones:
            if bone_name in humanoid_bones_to_preserve:
                # Preserve and rename Humanoid bones
                orig_bone = clothing_edit_bones[bone_name]
                new_name = f"origORS_{bone_name}"
                bone_data = {
                    'head': orig_bone.head.copy(),
                    'tail': orig_bone.tail.copy(),
                    'roll': orig_bone.roll,
                    'matrix': orig_bone.matrix.copy(),
                    'new_name': new_name,
                    'humanoid_name': clothing_bones_to_humanoid[bone_name],
                }
                original_bone_data[bone_name] = bone_data
                orig_bone.name = new_name
            else:
                # Delete non-Humanoid bones
                clothing_edit_bones.remove(clothing_edit_bones[bone_name])

    return original_bone_data


def create_new_bones(
    clothing_armature: bpy.types.Object,
    base_armature: bpy.types.Object,
    base_bones: set[str],
) -> dict[str, bpy.types.EditBone]:
    """Create new bones from base armature.

    Args:
        clothing_armature: Clothing armature object.
        base_armature: Base armature object.
        base_bones: Set of base bone names.

    Returns:
        Dictionary mapping bone names to new EditBone objects.
    """
    clothing_edit_bones = clothing_armature.data.edit_bones

    new_bones = {}
    for bone_name in base_bones:
        source_bone = base_armature.data.edit_bones.get(bone_name)
        if source_bone:
            new_bone = clothing_edit_bones.new(name=bone_name)
            copy_bone_transform(source_bone, new_bone)
            new_bones[bone_name] = new_bone

    return new_bones


def set_new_bone_parents(
    new_bones: dict[str, bpy.types.EditBone],
    base_bone_parents: dict[str, Optional[str]],
) -> None:
    """Set parent relationships for newly created bones.

    Args:
        new_bones: Dictionary of new EditBone objects.
        base_bone_parents: Dictionary of base bone parent relationships.
    """
    for bone_name, new_bone in new_bones.items():
        parent_name = base_bone_parents.get(bone_name)
        if parent_name and parent_name in new_bones:
            new_bone.parent = new_bones[parent_name]


def parent_original_bones_to_new(
    clothing_armature: bpy.types.Object,
    original_bone_data: dict[str, dict],
    new_bones: dict[str, bpy.types.EditBone],
    base_bone_to_humanoid: dict[str, str],
    clothing_avatar_data: dict,
    base_avatar_data: dict,
) -> None:
    """Make original humanoid bones children of new bones based on hierarchy.

    Args:
        clothing_armature: Clothing armature object.
        original_bone_data: Dictionary of original bone data.
        new_bones: Dictionary of new EditBone objects.
        base_bone_to_humanoid: Mapping from base bone names to humanoid names.
        clothing_avatar_data: Clothing avatar configuration data.
        base_avatar_data: Base avatar configuration data.
    """
    clothing_edit_bones = clothing_armature.data.edit_bones

    for orig_bone_name, data in original_bone_data.items():
        orig_bone = clothing_edit_bones[data['new_name']]
        humanoid_name = data['humanoid_name']

        # Find parent using boneHierarchy
        parent_humanoid_name = find_humanoid_parent_in_hierarchy(
            orig_bone_name, clothing_avatar_data, base_avatar_data
        )

        if parent_humanoid_name:
            matched_new_bone = _find_new_bone_by_humanoid_name(
                parent_humanoid_name, new_bones, base_bone_to_humanoid
            )
            if matched_new_bone:
                orig_bone.parent = matched_new_bone
            else:
                print(f"Warning: No matching new bone found for parent humanoid bone {parent_humanoid_name}")
        else:
            # Fallback to original matching logic
            matched_new_bone = _find_new_bone_by_humanoid_name(
                humanoid_name, new_bones, base_bone_to_humanoid
            )
            if matched_new_bone:
                orig_bone.parent = matched_new_bone
            else:
                print(f"Warning: No matching new bone found for humanoid bone {humanoid_name}")


def _find_new_bone_by_humanoid_name(
    humanoid_name: str,
    new_bones: dict[str, bpy.types.EditBone],
    base_bone_to_humanoid: dict[str, str],
) -> Optional[bpy.types.EditBone]:
    """Find a new bone by its humanoid name.

    Args:
        humanoid_name: Humanoid bone name to search for.
        new_bones: Dictionary of new EditBone objects.
        base_bone_to_humanoid: Mapping from base bone names to humanoid names.

    Returns:
        EditBone if found, None otherwise.
    """
    for new_bone_name, new_bone in new_bones.items():
        if new_bone_name in base_bone_to_humanoid:
            if base_bone_to_humanoid[new_bone_name] == humanoid_name:
                return new_bone
    return None


def apply_sub_humanoid_bone_substitution(
    parent_bones: dict[str, str],
    base_avatar_data: dict,
    base_bone_to_humanoid: dict[str, str],
) -> None:
    """Replace parent with subHumanoidBone if applicable.

    Args:
        parent_bones: Dictionary of parent bone relationships (modified in place).
        base_avatar_data: Base avatar configuration data.
        base_bone_to_humanoid: Mapping from base bone names to humanoid names.
    """
    if "subHumanoidBones" not in base_avatar_data:
        return

    sub_humanoid_bones = {}
    for sub_humanoid_bone in base_avatar_data["subHumanoidBones"]:
        sub_humanoid_bones[sub_humanoid_bone["humanoidBoneName"]] = sub_humanoid_bone["boneName"]

    for bone_name, parent_name in parent_bones.items():
        if parent_name in base_bone_to_humanoid:
            if base_bone_to_humanoid[parent_name] in sub_humanoid_bones.keys():
                parent_bones[bone_name] = sub_humanoid_bones[base_bone_to_humanoid[parent_name]]


def update_children_parents(
    clothing_armature: bpy.types.Object,
    children_to_update: list[str],
    parent_bones: dict[str, str],
) -> None:
    """Update parent relationships for children bones.

    Args:
        clothing_armature: Clothing armature object.
        children_to_update: List of bone names that need parent updates.
        parent_bones: Dictionary of parent bone relationships.
    """
    clothing_edit_bones = clothing_armature.data.edit_bones

    for child_name in children_to_update:
        child_bone = clothing_edit_bones.get(child_name)
        if child_bone:
            new_parent_name = parent_bones.get(child_name)
            if new_parent_name and new_parent_name in clothing_edit_bones:
                child_bone.parent = clothing_edit_bones[new_parent_name]

def finish_edit_mode() -> None:
    """Exit edit mode."""
    bpy.ops.object.mode_set(mode='OBJECT')
