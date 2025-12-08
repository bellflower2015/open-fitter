import os
import sys

# Add the parent directory (extracted/) to sys.path to allow imports from sibling directories
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def detect_finger_vertices(context):
    for humanoid_bone in context.finger_humanoid_bones:
        if humanoid_bone in context.humanoid_to_bone:
            bone_name = context.humanoid_to_bone[humanoid_bone]
            context.finger_bone_names.add(bone_name)
            if humanoid_bone in context.auxiliary_bones:
                for aux_bone in context.auxiliary_bones[humanoid_bone]:
                    context.finger_bone_names.add(aux_bone)

    if not context.finger_bone_names:
        return

    mesh = context.target_obj.data
    for bone_name in context.finger_bone_names:
        if bone_name in context.target_obj.vertex_groups:
            for vert in mesh.vertices:
                weight = 0.0
                for g in vert.groups:
                    if context.target_obj.vertex_groups[g.group].name == bone_name:
                        weight = g.weight
                        break
                if weight > 0.001:
                    context.finger_vertices.add(vert.index)
