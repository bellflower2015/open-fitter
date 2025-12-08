"""
post_processor - 後処理モジュール

遅延遷移の実行、マスク適用、クリーンアップを担当する。
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy
import numpy as np
from execute_transitions_with_cache import execute_transitions_with_cache
from mathutils import Vector


def execute_deferred_transitions(ctx):
    """
    遅延遷移をまとめて実行する。

    Args:
        ctx: SymmetricFieldDeformerContext インスタンス
    """
    if not ctx.deferred_transitions:
        return

    transition_operations, created_shape_key_mask_weights, used_shape_key_names = (
        execute_transitions_with_cache(
            ctx.deferred_transitions, ctx.transition_cache, ctx.target_obj
        )
    )

    for transition_operation in transition_operations:
        if transition_operation["transition_data"]["target_label"] == "Basis":
            ctx.non_transitioned_shape_vertices = [
                Vector(v) for v in transition_operation["initial_vertices"]
            ]
            break

    if used_shape_key_names:
        for config_shape_key_name in ctx.config_generated_shape_keys:
            if (
                config_shape_key_name not in used_shape_key_names
                and config_shape_key_name in ctx.target_obj.data.shape_keys.key_blocks
            ):
                ctx.shape_keys_to_remove.append(config_shape_key_name)

    for created_shape_key_name, mask_weights in created_shape_key_mask_weights.items():
        if created_shape_key_name in ctx.target_obj.data.shape_keys.key_blocks:
            ctx.config_generated_shape_keys[created_shape_key_name] = mask_weights
            ctx.non_relative_shape_keys.add(created_shape_key_name)
            ctx.config_blend_shape_labels.add(created_shape_key_name)
            ctx.label_to_target_shape_key_name[created_shape_key_name] = (
                created_shape_key_name
            )

def apply_masks_and_cleanup(ctx):
    """
    マスク適用と不要シェイプキー削除を実行する。

    Args:
        ctx: SymmetricFieldDeformerContext インスタンス
    """
    ctx.shape_key.value = 1.0

    basis_name = "Basis"
    basis_index = ctx.target_obj.data.shape_keys.key_blocks.find(basis_name)

    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = ctx.target_obj
    ctx.target_obj.select_set(True)

    if ctx.non_transitioned_shape_vertices:
        for additionalshape_key_name in ctx.additional_shape_keys:
            if additionalshape_key_name in ctx.target_obj.data.shape_keys.key_blocks:
                additional_shape_key = ctx.target_obj.data.shape_keys.key_blocks.get(
                    additionalshape_key_name
                )
                for i, vert in enumerate(additional_shape_key.data):
                    shape_diff = (
                        ctx.shape_key.data[i].co
                        - ctx.non_transitioned_shape_vertices[i]
                    )
                    additional_shape_key.data[i].co += shape_diff
            else:
                print(f"[Warning] {additionalshape_key_name} is not found in shape keys")

    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")

    for key_block in ctx.target_obj.data.shape_keys.key_blocks:
        pass  # Auto-inserted

    original_shape_key_name = f"{ctx.shape_key_name}_original"
    for sk in ctx.target_obj.data.shape_keys.key_blocks:
        if sk.name in ctx.non_relative_shape_keys and sk.name != basis_name:
            if ctx.shape_key_name in ctx.target_obj.data.shape_keys.key_blocks:
                ctx.target_obj.active_shape_key_index = (
                    ctx.target_obj.data.shape_keys.key_blocks.find(sk.name)
                )
                bpy.ops.mesh.blend_from_shape(shape=ctx.shape_key_name, blend=-1, add=True)
            else:
                print(
                    f"[Warning] {ctx.shape_key_name} or {ctx.shape_key_name}_original is not found in shape keys"
                )

    bpy.context.object.active_shape_key_index = basis_index
    bpy.ops.mesh.blend_from_shape(shape=ctx.shape_key_name, blend=1, add=True)

    bpy.ops.object.mode_set(mode="OBJECT")

    if original_shape_key_name in ctx.target_obj.data.shape_keys.key_blocks:
        original_shape_key = ctx.target_obj.data.shape_keys.key_blocks.get(
            original_shape_key_name
        )
        ctx.target_obj.shape_key_remove(original_shape_key)

    if ctx.shape_key:
        ctx.target_obj.shape_key_remove(ctx.shape_key)

    for unused_shape_key_name in ctx.shape_keys_to_remove:
        if unused_shape_key_name in ctx.target_obj.data.shape_keys.key_blocks:
            unused_shape_key = ctx.target_obj.data.shape_keys.key_blocks.get(
                unused_shape_key_name
            )
            if unused_shape_key:
                ctx.target_obj.shape_key_remove(unused_shape_key)
                print(
                    f"Removed shape key: {unused_shape_key_name} from {ctx.target_obj.name}"
                )
            else:
                print(f"[Warning] {unused_shape_key_name} is not found in shape keys")
        else:
            print(f"[Warning] {unused_shape_key_name} is not found in shape keys")

    if ctx.config_generated_shape_keys:
        print(
            f"Applying mask weights to generated shape keys: {list(ctx.config_generated_shape_keys.keys())}"
        )

        basis_shape_key = ctx.target_obj.data.shape_keys.key_blocks.get(basis_name)
        if basis_shape_key:
            basis_positions = np.array([v.co for v in basis_shape_key.data])

            for (
                shape_key_name_to_mask,
                mask_weights,
            ) in ctx.config_generated_shape_keys.items():
                if shape_key_name_to_mask == basis_name:
                    continue

                shape_key_to_mask = ctx.target_obj.data.shape_keys.key_blocks.get(
                    shape_key_name_to_mask
                )
                if shape_key_to_mask:
                    shape_positions = np.array([v.co for v in shape_key_to_mask.data])
                    displacement = shape_positions - basis_positions

                    if mask_weights is not None:
                        masked_displacement = displacement * mask_weights[:, np.newaxis]
                    else:
                        masked_displacement = displacement

                    new_positions = basis_positions + masked_displacement

                    for i, vertex in enumerate(shape_key_to_mask.data):
                        vertex.co = new_positions[i]

                    print(
                        f"Applied mask weights to shape key: {shape_key_name_to_mask}"
                    )


def finalize(ctx):
    """
    最終処理を実行する。

    Args:
        ctx: SymmetricFieldDeformerContext インスタンス
    """
    for sk in ctx.target_obj.data.shape_keys.key_blocks:
        sk.value = 0.0
