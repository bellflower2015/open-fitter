import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from blender_utils.blendshape_utils import apply_blendshape_values
from blender_utils.mesh_utils import cleanup_base_objects
from io_utils.avatar_data import load_avatar_data
from io_utils.file_io import import_base_fbx
from set_humanoid_bone_inherit_scale import set_humanoid_bone_inherit_scale


def process_base_avatar(base_fbx_path: str, avatar_data_path: str) -> tuple:
    """Process base avatar according to avatar data."""
    # Load avatar data
    avatar_data = load_avatar_data(avatar_data_path)
    
    # Import base FBX
    automatic_bone_orientation_int = avatar_data.get("enableAutomaticBoneOrientation", 0)
    if automatic_bone_orientation_int == 1:
        import_base_fbx(base_fbx_path, True)
    else:
        import_base_fbx(base_fbx_path, False)
    
    # Clean up objects and get references
    mesh_obj, armature_obj = cleanup_base_objects(avatar_data["meshName"])

    set_humanoid_bone_inherit_scale(armature_obj, avatar_data)
    
    # Apply blendshape values if they exist
    if mesh_obj and "blendshapes" in avatar_data:
        apply_blendshape_values(mesh_obj, avatar_data["blendshapes"])
    
    return mesh_obj, armature_obj, avatar_data
