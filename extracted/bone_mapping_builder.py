"""Bone mapping builder for humanoid bone replacement.

This module provides data structures and functions for building bone name mappings
from avatar data, used in the humanoid bone replacement process.
"""

from dataclasses import dataclass, field


@dataclass
class BoneMappings:
    """Container for all bone name mappings."""

    # Base avatar mappings
    base_humanoid_map: dict[str, str] = field(default_factory=dict)  # humanoidName -> boneName
    base_bone_to_humanoid: dict[str, str] = field(default_factory=dict)  # boneName -> humanoidName
    humanoid_to_aux_base: dict[str, list[str]] = field(default_factory=dict)

    # Clothing avatar mappings
    clothing_humanoid_map: dict[str, str] = field(default_factory=dict)  # boneName -> humanoidName
    clothing_bones_to_humanoid: dict[str, str] = field(default_factory=dict)
    aux_to_humanoid: dict[str, str] = field(default_factory=dict)
    humanoid_to_aux: dict[str, list[str]] = field(default_factory=dict)

    # Derived data
    missing_humanoid_bones: set[str] = field(default_factory=set)
    bones_to_replace: set[str] = field(default_factory=set)
    humanoid_bones_to_preserve: set[str] = field(default_factory=set)


def build_bone_mappings(
    base_avatar_data: dict,
    clothing_avatar_data: dict,
    preserve_humanoid_bones: bool,
) -> BoneMappings:
    """Build all bone mappings from avatar data.

    Args:
        base_avatar_data: Base avatar configuration data.
        clothing_avatar_data: Clothing avatar configuration data.
        preserve_humanoid_bones: Whether to preserve humanoid bones.

    Returns:
        BoneMappings containing all necessary mappings.
    """
    mappings = BoneMappings()

    # Base avatar mappings
    mappings.base_humanoid_map = {
        bone_map["humanoidBoneName"]: bone_map["boneName"]
        for bone_map in base_avatar_data["humanoidBones"]
    }
    mappings.base_bone_to_humanoid = {
        bone_map["boneName"]: bone_map["humanoidBoneName"]
        for bone_map in base_avatar_data["humanoidBones"]
    }

    # Clothing avatar mappings
    mappings.clothing_humanoid_map = {
        bone_map["boneName"]: bone_map["humanoidBoneName"]
        for bone_map in clothing_avatar_data["humanoidBones"]
    }
    mappings.clothing_bones_to_humanoid = mappings.clothing_humanoid_map.copy()

    # Note: missing_humanoid_bones is intentionally empty for now
    mappings.missing_humanoid_bones = set()

    # Build auxiliary mappings
    _build_auxiliary_mappings(mappings, base_avatar_data, clothing_avatar_data)

    # Build bones to replace
    _build_bones_to_replace(mappings, clothing_avatar_data)

    # Build humanoid bones to preserve
    if preserve_humanoid_bones:
        mappings.humanoid_bones_to_preserve = {
            bone_name
            for bone_name, humanoid_name in mappings.clothing_bones_to_humanoid.items()
            if humanoid_name not in mappings.missing_humanoid_bones
        }

    return mappings


def _build_auxiliary_mappings(
    mappings: BoneMappings,
    base_avatar_data: dict,
    clothing_avatar_data: dict,
) -> None:
    """Build auxiliary bone mappings.

    Args:
        mappings: BoneMappings to update.
        base_avatar_data: Base avatar configuration data.
        clothing_avatar_data: Clothing avatar configuration data.
    """
    # Map auxiliary bones to humanoid bones (clothing)
    for aux_set in clothing_avatar_data.get("auxiliaryBones", []):
        humanoid_bone = aux_set["humanoidBoneName"]
        if humanoid_bone not in mappings.missing_humanoid_bones:
            for aux_bone in aux_set["auxiliaryBones"]:
                mappings.aux_to_humanoid[aux_bone] = humanoid_bone
            mappings.humanoid_to_aux[humanoid_bone] = aux_set["auxiliaryBones"]

    # Map humanoid bones to auxiliary bones (base)
    for aux_set in base_avatar_data.get("auxiliaryBones", []):
        mappings.humanoid_to_aux_base[aux_set["humanoidBoneName"]] = aux_set["auxiliaryBones"]


def _build_bones_to_replace(mappings: BoneMappings, clothing_avatar_data: dict) -> None:
    """Build the set of bones to be replaced.

    Args:
        mappings: BoneMappings to update.
        clothing_avatar_data: Clothing avatar configuration data.
    """
    for bone_map in clothing_avatar_data["humanoidBones"]:
        if bone_map["humanoidBoneName"] not in mappings.missing_humanoid_bones:
            mappings.bones_to_replace.add(bone_map["boneName"])

    for aux_set in clothing_avatar_data.get("auxiliaryBones", []):
        if aux_set["humanoidBoneName"] not in mappings.missing_humanoid_bones:
            mappings.bones_to_replace.update(aux_set["auxiliaryBones"])
