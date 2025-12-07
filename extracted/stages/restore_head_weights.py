import os
import sys

# Add the parent directory (extracted/) to sys.path to allow imports from sibling directories
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time

def restore_head_weights(context):
    head_time_start = time.time()
    head_bone_name = None
    if context.base_avatar_data and "humanoidBones" in context.base_avatar_data:
        for bone_data in context.base_avatar_data["humanoidBones"]:
            if bone_data.get("humanoidBoneName", "") == "Head":
                head_bone_name = bone_data.get("boneName", "")
                break

    if head_bone_name and head_bone_name in context.target_obj.vertex_groups:
        print(f"  Headボーンウェイトを処理中: {head_bone_name}")
        head_vertices_count = 0
        for vert_idx in range(len(context.target_obj.data.vertices)):
            original_head_weight = 0.0
            if vert_idx in context.original_humanoid_weights:
                original_head_weight = context.original_humanoid_weights[vert_idx].get(head_bone_name, 0.0)
            current_head_weight = 0.0
            for g in context.target_obj.data.vertices[vert_idx].groups:
                if g.group == context.target_obj.vertex_groups[head_bone_name].index:
                    current_head_weight = g.weight
                    break
            head_weight_diff = original_head_weight - current_head_weight
            if original_head_weight > 0.0:
                context.target_obj.vertex_groups[head_bone_name].add([vert_idx], original_head_weight, "REPLACE")
            else:
                try:
                    context.target_obj.vertex_groups[head_bone_name].remove([vert_idx])
                except RuntimeError:
                    pass
            if abs(head_weight_diff) > 0.0001 and vert_idx in context.original_humanoid_weights:
                for group in context.target_obj.vertex_groups:
                    if group.name in context.bone_groups and group.name != head_bone_name:
                        original_weight = context.original_humanoid_weights[vert_idx].get(group.name, 0.0)
                        if original_weight > 0.0:
                            current_weight = 0.0
                            for g in context.target_obj.data.vertices[vert_idx].groups:
                                if g.group == group.index:
                                    current_weight = g.weight
                                    break
                            new_weight = current_weight + (original_weight * head_weight_diff)
                            if new_weight > 0.0:
                                group.add([vert_idx], new_weight, "REPLACE")
                            else:
                                try:
                                    group.remove([vert_idx])
                                except RuntimeError:
                                    pass

            total_weight = 0.0
            for g in context.target_obj.data.vertices[vert_idx].groups:
                group_name = context.target_obj.vertex_groups[g.group].name
                if group_name in context.all_deform_groups:
                    total_weight += g.weight
            if total_weight < 0.9999 and vert_idx in context.original_humanoid_weights:
                weight_shortage = 1.0 - total_weight
                for group in context.target_obj.vertex_groups:
                    if group.name in context.bone_groups:
                        original_weight = context.original_humanoid_weights[vert_idx].get(group.name, 0.0)
                        if original_weight > 0.0:
                            current_weight = 0.0
                            for g in context.target_obj.data.vertices[vert_idx].groups:
                                if g.group == group.index:
                                    current_weight = g.weight
                                    break
                            additional_weight = original_weight * weight_shortage
                            new_weight = current_weight + additional_weight
                            group.add([vert_idx], new_weight, "REPLACE")
            head_vertices_count += 1
        if head_vertices_count > 0:
            print(f"  Headウェイト処理完了: {head_vertices_count}頂点")
    head_time = time.time() - head_time_start
    print(f"  Headウェイト処理: {head_time:.2f}秒")
