import os
import sys

# Add the parent directory (extracted/) to sys.path to allow imports from sibling directories
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time


def blend_results(context):
    for vert_idx in range(len(context.target_obj.data.vertices)):
        falloff_weight = 0.0
        for g in context.target_obj.data.vertices[vert_idx].groups:
            if g.group == context.distance_falloff_group.index:
                falloff_weight = g.weight
                break
        for group_name in context.bone_groups:
            if group_name in context.target_obj.vertex_groups:
                weight_a = context.weights_a[vert_idx].get(group_name, 0.0)
                weight_b = context.weights_b[vert_idx].get(group_name, 0.0)
                final_weight = (weight_a * falloff_weight) + (weight_b * (1.0 - falloff_weight))
                group = context.target_obj.vertex_groups[group_name]
                if final_weight > 0:
                    group.add([vert_idx], final_weight, "REPLACE")
                else:
                    try:
                        group.remove([vert_idx])
                    except RuntimeError:
                        pass
