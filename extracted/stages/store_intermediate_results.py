import os
import sys

# Add the parent directory (extracted/) to sys.path to allow imports from sibling directories
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time


def store_intermediate_results(context):
    for vert_idx in range(len(context.target_obj.data.vertices)):
        context.weights_a[vert_idx] = {}
        for group in context.target_obj.vertex_groups:
            if group.name in context.bone_groups:
                try:
                    weight = 0.0
                    for g in context.target_obj.data.vertices[vert_idx].groups:
                        if g.group == group.index:
                            weight = g.weight
                            break
                    context.weights_a[vert_idx][group.name] = weight
                except Exception:
                    continue
    for vert_idx in range(len(context.target_obj.data.vertices)):
        context.weights_b[vert_idx] = {}
        for group in context.target_obj.vertex_groups:
            if group.name in context.bone_groups:
                try:
                    weight = 0.0
                    for g in context.target_obj.data.vertices[vert_idx].groups:
                        if g.group == group.index:
                            weight = g.weight
                            break
                    context.weights_b[vert_idx][group.name] = weight
                except Exception:
                    continue
    for sway_bone in context.base_avatar_data.get("swayBones", []):
        parent_bone = sway_bone["parentBoneName"]
        for affected_bone in sway_bone["affectedBones"]:
            for vert_idx in context.weights_b:
                if affected_bone in context.weights_b[vert_idx]:
                    affected_weight = context.weights_b[vert_idx][affected_bone]
                    if parent_bone not in context.weights_b[vert_idx]:
                        context.weights_b[vert_idx][parent_bone] = 0.0
                    context.weights_b[vert_idx][parent_bone] += affected_weight
                    del context.weights_b[vert_idx][affected_bone]
