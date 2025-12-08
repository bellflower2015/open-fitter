"""Parent bone finder for humanoid bone replacement.

This module provides functions for finding parent bones using weight-based scoring
and fallback distance comparison.
"""

from collections import defaultdict
from typing import Optional

import bmesh
import bpy
from mathutils.bvhtree import BVHTree


def find_parent_bones(
    clothing_bone_data: dict[str, dict],
    clothing_meshes: list,
    base_armature: bpy.types.Object,
    clothing_armature: bpy.types.Object,
    bvh: BVHTree,
    bmesh_data: bmesh.types.BMesh,
    base_mesh: bpy.types.Object,
    base_group_index_to_name: dict[int, str],
) -> dict[str, str]:
    """Find parent bones for each clothing bone using weight-based scoring.

    Args:
        clothing_bone_data: Dictionary containing bone data with head positions and candidates.
        clothing_meshes: List of clothing mesh objects.
        base_armature: Base armature object.
        clothing_armature: Clothing armature object.
        bvh: BVH tree for spatial queries.
        bmesh_data: BMesh data for the base mesh.
        base_mesh: Base mesh object.
        base_group_index_to_name: Mapping from vertex group index to name.

    Returns:
        Dictionary mapping bone names to their chosen parent bone names.
    """
    parent_bones = {}

    for bone_name, data in clothing_bone_data.items():
        chosen_parent = _find_parent_for_bone(
            bone_name,
            data,
            clothing_meshes,
            base_armature,
            clothing_armature,
            bvh,
            bmesh_data,
            base_mesh,
            base_group_index_to_name,
        )
        parent_bones[bone_name] = chosen_parent
    return parent_bones


def _find_parent_for_bone(
    bone_name: str,
    data: dict,
    clothing_meshes: list,
    base_armature: bpy.types.Object,
    clothing_armature: bpy.types.Object,
    bvh: BVHTree,
    bmesh_data: bmesh.types.BMesh,
    base_mesh: bpy.types.Object,
    base_group_index_to_name: dict[int, str],
) -> str:
    """Find the best parent bone for a single clothing bone.

    Args:
        bone_name: Name of the bone to find parent for.
        data: Bone data containing head position and candidates.
        clothing_meshes: List of clothing mesh objects.
        base_armature: Base armature object.
        clothing_armature: Clothing armature object.
        bvh: BVH tree for spatial queries.
        bmesh_data: BMesh data for the base mesh.
        base_mesh: Base mesh object.
        base_group_index_to_name: Mapping from vertex group index to name.

    Returns:
        Name of the chosen parent bone.
    """
    head_pos = data['head_pos']
    candidate_bones = data['candidate_bones']
    parent_humanoid = data['parent_humanoid']
    sub_parent_humanoid = data.get('sub_parent_humanoid', None)

    # Score candidate bones based on vertex weights
    bone_scores = _calculate_bone_scores(
        bone_name,
        candidate_bones,
        clothing_meshes,
        bvh,
        bmesh_data,
        base_mesh,
        base_group_index_to_name,
    )

    chosen_parent = None
    if bone_scores:
        chosen_parent = max(bone_scores.items(), key=lambda item: item[1])[0]

    # Avoid self-reference
    if chosen_parent and chosen_parent == bone_name:
        if bone_name in clothing_armature.data.bones:
            parent_bone = clothing_armature.data.bones.get(bone_name).parent
            if parent_bone:
                chosen_parent = parent_bone.name
                if chosen_parent not in candidate_bones:
                    chosen_parent = None

    if chosen_parent:
        return chosen_parent

    # Fallback: use distance comparison if sub_parent_humanoid exists
    return _fallback_parent_selection(head_pos, parent_humanoid, sub_parent_humanoid, base_armature)


def _calculate_bone_scores(
    bone_name: str,
    candidate_bones: set[str],
    clothing_meshes: list,
    bvh: BVHTree,
    bmesh_data: bmesh.types.BMesh,
    base_mesh: bpy.types.Object,
    base_group_index_to_name: dict[int, str],
) -> dict[str, float]:
    """Calculate weight scores for candidate bones based on clothing mesh vertices.

    Args:
        bone_name: Name of the bone to calculate scores for.
        candidate_bones: Set of candidate bone names.
        clothing_meshes: List of clothing mesh objects.
        bvh: BVH tree for spatial queries.
        bmesh_data: BMesh data for the base mesh.
        base_mesh: Base mesh object.
        base_group_index_to_name: Mapping from vertex group index to name.

    Returns:
        Dictionary mapping bone names to their weight scores.
    """
    bone_scores = defaultdict(float)
    weighted_vertices = []

    for mesh_obj in clothing_meshes:
        if mesh_obj.type != 'MESH':
            continue

        vg_lookup = {vg.name: vg.index for vg in mesh_obj.vertex_groups}
        if bone_name not in vg_lookup:
            continue

        target_group_index = vg_lookup[bone_name]
        mesh_data = mesh_obj.data
        mesh_world_matrix = mesh_obj.matrix_world

        for vertex in mesh_data.vertices:
            weight = 0.0
            for g in vertex.groups:
                if g.group == target_group_index:
                    weight = g.weight
                    break
            if weight >= 0.001:
                vertex_world_co = mesh_world_matrix @ vertex.co
                weighted_vertices.append((vertex_world_co, weight))

    if weighted_vertices:
        weighted_vertices.sort(key=lambda item: item[1], reverse=True)
        top_vertices = weighted_vertices[:100]

        for vertex_world_co, _ in top_vertices:
            closest_point, _, face_idx, _ = bvh.find_nearest(vertex_world_co)
            if closest_point is None or face_idx is None:
                continue

            face = bmesh_data.faces[face_idx]
            vertex_indices = [v.index for v in face.verts]
            closest_vert_idx = min(
                vertex_indices,
                key=lambda idx: (base_mesh.data.vertices[idx].co - closest_point).length,
            )

            vertex = base_mesh.data.vertices[closest_vert_idx]
            for group_element in vertex.groups:
                group_name = base_group_index_to_name.get(group_element.group)
                if group_name in candidate_bones:
                    bone_scores[group_name] += group_element.weight

    return bone_scores


def _fallback_parent_selection(
    head_pos,
    parent_humanoid: str,
    sub_parent_humanoid: Optional[str],
    base_armature: bpy.types.Object,
) -> str:
    """Fallback parent selection using distance comparison.

    Args:
        head_pos: World position of the bone head.
        parent_humanoid: Name of the parent humanoid bone.
        sub_parent_humanoid: Name of the sub-parent humanoid bone (optional).
        base_armature: Base armature object.

    Returns:
        Name of the chosen parent bone.
    """
    if sub_parent_humanoid:
        parent_humanoid_bone = base_armature.pose.bones.get(parent_humanoid)
        sub_parent_humanoid_bone = base_armature.pose.bones.get(sub_parent_humanoid)

        if parent_humanoid_bone and sub_parent_humanoid_bone:
            parent_distance = (head_pos - (base_armature.matrix_world @ parent_humanoid_bone.head)).length
            sub_parent_distance = (
                head_pos - (base_armature.matrix_world @ sub_parent_humanoid_bone.head)
            ).length

            if sub_parent_distance < parent_distance:
                print(
                    f"chosen_parent: {sub_parent_humanoid} (sub_parent, distance: {sub_parent_distance:.4f})"
                )
                return sub_parent_humanoid
            else:
                print(f"chosen_parent: {parent_humanoid} (fallback, distance: {parent_distance:.4f})")
                return parent_humanoid
        else:
            print(f"chosen_parent: {parent_humanoid} (fallback)")
            return parent_humanoid
    else:
        print(f"chosen_parent: {parent_humanoid} (fallback)")
        return parent_humanoid
