import os
import sys

# Add the parent directory (extracted/) to sys.path to allow imports from sibling directories
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time


def compare_side_and_bone_weights(context):
    side_left_group = context.target_obj.vertex_groups.get("LeftSideWeights")
    side_right_group = context.target_obj.vertex_groups.get("RightSideWeights")
    failed_vertices_count = 0
    if side_left_group and side_right_group:
        for vert in context.target_obj.data.vertices:
            total_side_weight = 0.0
            for g in vert.groups:
                if g.group == side_left_group.index or g.group == side_right_group.index:
                    total_side_weight += g.weight
            total_side_weight = min(total_side_weight, 1.0)
            total_side_weight = total_side_weight - context.non_humanoid_total_weights[vert.index]
            total_side_weight = max(total_side_weight, 0.0)

            total_bone_weight = 0.0
            for g in vert.groups:
                group_name = context.target_obj.vertex_groups[g.group].name
                if group_name in context.bone_groups:
                    total_bone_weight += g.weight

            if total_side_weight > total_bone_weight + 0.5:
                for group in context.target_obj.vertex_groups:
                    if group.name in context.bone_groups:
                        try:
                            group.remove([vert.index])
                        except RuntimeError:
                            continue
                if vert.index in context.original_humanoid_weights:
                    for group_name, weight in context.original_humanoid_weights[vert.index].items():
                        if group_name in context.target_obj.vertex_groups:
                            context.target_obj.vertex_groups[group_name].add([vert.index], weight, "REPLACE")
                failed_vertices_count += 1
