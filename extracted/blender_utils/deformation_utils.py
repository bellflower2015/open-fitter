import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from algo_utils.bone_group_utils import get_deformation_bone_groups
from algo_utils.vertex_group_utils import get_vertex_groups_and_weights
from blender_utils.bone_utils import get_deformation_bones
from mathutils import Matrix
from mathutils import Matrix, Vector
from mathutils import Vector
from misc_utils.globals import _deformation_field_cache
from scipy.spatial import cKDTree
import bpy
import numpy as np
import os
import sys

# Merged from batch_process_vertices_multi_step.py

def batch_process_vertices_multi_step(vertices, all_field_points, all_delta_positions, field_weights, 
                                     field_matrix, field_matrix_inv, target_matrix, target_matrix_inv, 
                                     deform_weights=None, rbf_epsilon=0.00001, batch_size=1000, k=8):
    """
    多段階のDeformation Fieldを使用して頂点を処理する（SaveAndApplyFieldAuto.pyのapply_field_dataと同様）
    
    Parameters:
        vertices: 処理対象の頂点配列
        all_field_points: 各ステップのフィールドポイント配列
        all_delta_positions: 各ステップのデルタポジション配列
        field_weights: フィールドウェイト
        field_matrix: フィールドマトリックス
        field_matrix_inv: フィールドマトリックスの逆行列
        target_matrix: ターゲットマトリックス
        target_matrix_inv: ターゲットマトリックスの逆行列
        rbf_epsilon: RBF補間のイプシロン値
        batch_size: バッチサイズ
        k: 近傍点数
        
    Returns:
        変形後の頂点配列（ワールド座標）
    """
    num_vertices = len(vertices)
    num_steps = len(all_field_points)
    
    # 累積変位を初期化
    cumulative_displacements = np.zeros((num_vertices, 3))
    # 現在の頂点位置（ワールド座標）を保存
    current_world_positions = np.array([target_matrix @ Vector(v) for v in vertices])

    # もしdeform_weightsがNoneの場合は、全ての頂点のウェイトを1.0とする
    if deform_weights is None:
        deform_weights = np.ones(num_vertices)
    
    # 各ステップの変位を累積的に適用
    for step in range(num_steps):
        field_points = all_field_points[step]
        delta_positions = all_delta_positions[step]
        
        # KDTreeを使用して近傍点を検索（各ステップで新しいKDTreeを構築）
        kdtree = cKDTree(field_points)
        
        # カスタムRBF補間で新しい頂点位置を計算
        step_displacements = np.zeros((num_vertices, 3))
        
        for start_idx in range(0, num_vertices, batch_size):
            end_idx = min(start_idx + batch_size, num_vertices)
            batch_weights = deform_weights[start_idx:end_idx]
            
            # バッチ内の全頂点をフィールド空間に変換（現在の累積変位を考慮）
            batch_world = current_world_positions[start_idx:end_idx].copy()
            batch_field = np.array([field_matrix_inv @ Vector(v) for v in batch_world])
            
            # 各頂点ごとに逆距離加重法で補間
            batch_displacements = np.zeros((len(batch_field), 3))
            
            for i, point in enumerate(batch_field):
                # 近傍点を検索（最大k点）
                k_use = min(k, len(field_points))
                distances, indices = kdtree.query(point, k=k_use)
                
                # 距離が0の場合（完全に一致する点がある場合）
                if distances[0] < 1e-10:
                    batch_displacements[i] = delta_positions[indices[0]]
                    continue
                
                # 逆距離の重みを計算
                weights = 1.0 / np.sqrt(distances**2 + rbf_epsilon**2)
                
                # 重みの正規化
                weights /= np.sum(weights)
                
                # 重み付き平均で変位を計算
                weighted_deltas = delta_positions[indices] * weights[:, np.newaxis]
                batch_displacements[i] = np.sum(weighted_deltas, axis=0) * batch_weights[i]
            
            # ワールド空間での変位を計算
            for i, displacement in enumerate(batch_displacements):
                world_displacement = field_matrix.to_3x3() @ Vector(displacement)
                step_displacements[start_idx + i] = world_displacement
                
                # 現在のワールド位置を更新（次のステップのために）
                current_world_positions[start_idx + i] += world_displacement
        
        # このステップの変位を累積変位に追加
        cumulative_displacements += step_displacements
        
        #print(f"ステップ {step+1} 完了: 最大変位 {np.max(np.linalg.norm(step_displacements, axis=1)):.6f}")
    
    # 最終的な変形後の位置を返す
    final_world_positions = np.array([target_matrix @ Vector(v) for v in vertices]) + cumulative_displacements
    return final_world_positions

# Merged from batch_process_vertices_with_custom_range.py

def batch_process_vertices_with_custom_range(vertices, all_field_points, all_delta_positions, field_weights, 
                                            field_matrix, field_matrix_inv, target_matrix, target_matrix_inv, 
                                            start_value, end_value, 
                                            deform_weights=None, rbf_epsilon=0.00001, batch_size=1000, k=8):
    """
    任意の値の範囲でフィールドによる変形を行う
    
    Parameters:
        vertices: 処理対象の頂点配列
        all_field_points: 各ステップのフィールドポイント配列
        all_delta_positions: 各ステップのデルタポジション配列
        field_weights: フィールドウェイト
        field_matrix: フィールドマトリックス
        field_matrix_inv: フィールドマトリックスの逆行列
        target_matrix: ターゲットマトリックス
        target_matrix_inv: ターゲットマトリックスの逆行列
        start_value: 開始値（シェイプキー値）
        end_value: 終了値（シェイプキー値）
        deform_weights: 変形ウェイト
        rbf_epsilon: RBF補間のイプシロン値
        batch_size: バッチサイズ
        k: 近傍点数
        
    Returns:
        変形後の頂点配列（ワールド座標）
    """
    num_vertices = len(vertices)
    num_steps = len(all_field_points)
    
    # 累積変位を初期化
    cumulative_displacements = np.zeros((num_vertices, 3))
    # 現在の頂点位置（ワールド座標）を保存
    current_world_positions = np.array([target_matrix @ Vector(v) for v in vertices])

    # もしdeform_weightsがNoneの場合は、全ての頂点のウェイトを1.0とする
    if deform_weights is None:
        deform_weights = np.ones(num_vertices)
    
    # ステップごとの値を計算
    step_size = 1.0 / num_steps
    
    # 各ステップで処理
    processed_steps = []
    for step in range(num_steps):
        step_start = step * step_size
        step_end = (step + 1) * step_size
        # start_valueからend_valueに増加（start_value < end_value）
        if step_start + 0.00001 <= end_value and step_end - 0.00001 >= start_value:
            processed_steps.append((step, step_start, step_end))
    
    # 各ステップの変位を累積的に適用
    for step_idx, (step, step_start, step_end) in enumerate(processed_steps):
        field_points = all_field_points[step].copy()
        delta_positions = all_delta_positions[step].copy()
        original_delta_positions = all_delta_positions[step].copy()
        
        # 任意の値からの変形
        if start_value != step_start:
            if start_value >= step_start + 0.00001:
                # 開始値がステップの開始値より大きい場合
                adjustment_factor = (start_value - step_start) / step_size
                adjustment_delta = original_delta_positions * adjustment_factor
                field_points += adjustment_delta
                delta_positions -= adjustment_delta
        if end_value != step_end:
            if end_value <= step_end - 0.00001:
                # 終了値がステップの終了値より小さい場合
                adjustment_factor = (step_end - end_value) / step_size
                adjustment_delta = original_delta_positions * adjustment_factor
                delta_positions -= adjustment_delta
        
        # KDTreeを使用して近傍点を検索
        kdtree = cKDTree(field_points)
        
        # カスタムRBF補間で新しい頂点位置を計算
        step_displacements = np.zeros((num_vertices, 3))
        
        for start_idx in range(0, num_vertices, batch_size):
            end_idx = min(start_idx + batch_size, num_vertices)
            batch_weights = deform_weights[start_idx:end_idx]
            
            # バッチ内の全頂点をフィールド空間に変換
            batch_world = current_world_positions[start_idx:end_idx].copy()
            batch_field = np.array([field_matrix_inv @ Vector(v) for v in batch_world])
            
            # 各頂点ごとに逆距離加重法で補間
            batch_displacements = np.zeros((len(batch_field), 3))
            
            for i, point in enumerate(batch_field):
                # 近傍点を検索（最大k点）
                k_use = min(k, len(field_points))
                distances, indices = kdtree.query(point, k=k_use)
                
                # 距離が0の場合（完全に一致する点がある場合）
                if distances[0] < 1e-10:
                    batch_displacements[i] = delta_positions[indices[0]]
                    continue
                
                # 逆距離の重みを計算
                weights = 1.0 / np.sqrt(distances**2 + rbf_epsilon**2)
                
                # 重みの正規化
                weights /= np.sum(weights)
                
                # 重み付き平均で変位を計算
                weighted_deltas = delta_positions[indices] * weights[:, np.newaxis]
                batch_displacements[i] = np.sum(weighted_deltas, axis=0) * batch_weights[i]
            
            # ワールド空間での変位を計算
            for i, displacement in enumerate(batch_displacements):
                world_displacement = field_matrix.to_3x3() @ Vector(displacement)
                step_displacements[start_idx + i] = world_displacement
                
                # 現在のワールド位置を更新（次のステップのために）
                current_world_positions[start_idx + i] += world_displacement
        
        # このステップの変位を累積変位に追加
        cumulative_displacements += step_displacements
        
    
    # 最終的な変形後の位置を返す
    final_world_positions = np.array([target_matrix @ Vector(v) for v in vertices]) + cumulative_displacements
    return final_world_positions

# Merged from inverse_bone_deform_all_vertices.py

def _validate_inputs(armature_obj, mesh_obj):
    if not armature_obj or armature_obj.type != 'ARMATURE':
        raise ValueError("有効なArmatureオブジェクトを指定してください")

    if not mesh_obj or mesh_obj.type != 'MESH':
        raise ValueError("有効なメッシュオブジェクトを指定してください")


def _gather_world_vertices(mesh_obj):
    return [v.co.copy() for v in mesh_obj.data.vertices]


def _compute_combined_matrix(weights, armature_obj):
    combined_matrix = Matrix.Identity(4)
    combined_matrix.zero()
    total_weight = 0.0

    for bone_name, weight in weights.items():
        if weight > 0 and bone_name in armature_obj.data.bones:
            bone = armature_obj.data.bones[bone_name]
            pose_bone = armature_obj.pose.bones.get(bone_name)
            if bone and pose_bone:
                bone_matrix = pose_bone.matrix @ bone.matrix_local.inverted()
                combined_matrix += bone_matrix * weight
                total_weight += weight

    return combined_matrix, total_weight


def _safe_inverse_matrix(combined_matrix, vertex_index):
    try:
        return combined_matrix.inverted()
    except Exception:
        return Matrix.Identity(4)


def _log_progress(vertex_index, total_vertices):
    if (vertex_index + 1) % 1000 == 0:
        pass  # Progress logging disabled

def _compute_inverse_vertices(vertices, mesh_obj, armature_obj):
    inverse_transformed_vertices = []

    for vertex_index, pos in enumerate(vertices):
        weights = get_vertex_groups_and_weights(mesh_obj, vertex_index)

        if not weights:
            inverse_transformed_vertices.append(pos)
            _log_progress(vertex_index, len(vertices))
            continue

        combined_matrix, total_weight = _compute_combined_matrix(weights, armature_obj)

        if total_weight > 0:
            combined_matrix = combined_matrix * (1.0 / total_weight)
        else:
            combined_matrix = Matrix.Identity(4)

        inverse_matrix = _safe_inverse_matrix(combined_matrix, vertex_index)
        rest_pose_pos = inverse_matrix @ pos

        inverse_transformed_vertices.append(rest_pose_pos)
        _log_progress(vertex_index, len(vertices))

    return inverse_transformed_vertices


def _apply_inverse_to_shape_keys(mesh_obj, inverse_transformed_vertices, original_vertices):
    if not mesh_obj.data.shape_keys:
        return

    for shape_key in mesh_obj.data.shape_keys.key_blocks:
        if shape_key.name != "Basis":
            for i, vert in enumerate(shape_key.data):
                vert.co += inverse_transformed_vertices[i] - original_vertices[i]

    basis_shape_key = mesh_obj.data.shape_keys.key_blocks["Basis"]
    for i, vert in enumerate(basis_shape_key.data):
        vert.co = inverse_transformed_vertices[i]


def _apply_inverse_to_mesh(mesh_obj, inverse_transformed_vertices):
    for vertex_index, pos in enumerate(inverse_transformed_vertices):
        mesh_obj.data.vertices[vertex_index].co = pos


def inverse_bone_deform_all_vertices(armature_obj, mesh_obj):
    """
    メッシュオブジェクトの評価後の頂点のワールド座標から、
    現在のArmatureオブジェクトのポーズの逆変換をすべての頂点に対して行う
    
    Parameters:
        armature_obj: Armatureオブジェクト
        mesh_obj: メッシュオブジェクト
        
    Returns:
        np.ndarray: すべての頂点の逆変換後の座標（ローカル座標）
        

        通常のボーン変形: 変形後 = Σ(weight_i × bone_matrix_i) × 変形前
        この関数の逆変換: 変形前 = [Σ(weight_i × bone_matrix_i)]^(-1) × 変形後
    """
    _validate_inputs(armature_obj, mesh_obj)

    vertices = _gather_world_vertices(mesh_obj)

    inverse_transformed_vertices = _compute_inverse_vertices(vertices, mesh_obj, armature_obj)

    _apply_inverse_to_shape_keys(mesh_obj, inverse_transformed_vertices, vertices)
    _apply_inverse_to_mesh(mesh_obj, inverse_transformed_vertices)

    result = np.array([[v[0], v[1], v[2]] for v in inverse_transformed_vertices])

    return result

# Merged from apply_bone_field_delta.py

def apply_bone_field_delta(armature_obj: bpy.types.Object, field_data_path: str, avatar_data: dict) -> None:
    """
    ボーンにDeformation Fieldを適用
    
    Parameters:
        armature_obj: アーマチュアオブジェクト
        field_data_path: Deformation Fieldデータのパス
        avatar_data: アバターデータ
    """
    # データの読み込み
    field_info = get_deformation_field_multi_step(field_data_path)
    all_field_points = field_info['all_field_points']
    all_delta_positions = field_info['all_delta_positions']
    all_field_weights = field_info['field_weights']
    field_matrix = field_info['world_matrix']
    field_matrix_inv = field_info['world_matrix_inv']
    k_neighbors = field_info['kdtree_query_k']
    
    # 変形対象のボーンを取得
    deform_bones = get_deformation_bones(armature_obj, avatar_data)

    bpy.ops.object.mode_set(mode='OBJECT')
    
    # すべての選択を解除
    bpy.ops.object.select_all(action='DESELECT')

    # アクティブオブジェクトを設定
    armature_obj.select_set(True)
    bpy.context.view_layer.objects.active = armature_obj

    # ------------------------------------------------------------------
    # 【追加処理：処理前の親子Head位置の記録】
    # deform_bones内で「子が１つのみ」のボーンについて、親ボーンとその子ボーンの
    # ワールド空間でのHead位置を記録しておく。
    # ------------------------------------------------------------------
    original_heads = {}
    for bone in armature_obj.pose.bones:
        if bone.name in deform_bones and len(bone.children) == 1:
            child = bone.children[0]
            parent_head_world = armature_obj.matrix_world @ (bone.matrix @ Vector((0, 0, 0)))
            child_head_world = armature_obj.matrix_world @ (child.matrix @ Vector((0, 0, 0)))
            # コピーして記録（後で参照するため）
            original_heads[bone.name] = (parent_head_world.copy(), child_head_world.copy())
    
    def process_bone_hierarchy(bone_name, parent_world_displacement, kdtree, delta_positions):
        """ボーン階層を再帰的に処理"""
        
        bone = armature_obj.pose.bones[bone_name]
        ret_displacement = parent_world_displacement

        if bone_name in deform_bones:
            base_matrix = armature_obj.data.bones[bone.name].matrix_local
            current_world_matrix = armature_obj.matrix_world @ (bone.matrix @ base_matrix.inverted())
               
            # ヘッドの位置を取得
            head_world = (armature_obj.matrix_world @ bone.matrix @ Vector((0, 0, 0))) - parent_world_displacement
            
            # ヘッドのフィールド空間での座標を計算
            head_field = field_matrix_inv @ head_world
        
            # ヘッドの最近接点の検索
            head_distances, head_indices = kdtree.query(head_field, k=k_neighbors)
        
            # ヘッドの変位を計算
            weights = 1.0 / (head_distances + 0.0001)
            weights /= weights.sum()
            deltas = delta_positions[head_indices]
            head_displacement = (deltas * weights[:, np.newaxis]).sum(axis=0)

            # ワールド空間での変位を計算
            world_displacement = (field_matrix.to_3x3() @ Vector(head_displacement)) - parent_world_displacement

            new_matrix = Matrix.Translation(world_displacement)
            combined_matrix = new_matrix @ current_world_matrix
            bone.matrix = armature_obj.matrix_world.inverted() @ combined_matrix @ base_matrix

            ret_displacement = world_displacement + parent_world_displacement
        
        # 子ボーンを処理
        for child in bone.children:
            process_bone_hierarchy(child.name, ret_displacement, kdtree, delta_positions)
    
    # 各ステップの変位を累積的に適用
    num_steps = len(all_field_points)
    for step in range(num_steps):
        field_points = all_field_points[step]
        delta_positions = all_delta_positions[step]
        # KDTreeを使用して近傍点を検索（各ステップで新しいKDTreeを構築）
        kdtree = cKDTree(field_points)

        # ルートボーンから処理を開始
        root_displacement = Vector((0, 0, 0))
        root_bones = [bone.name for bone in armature_obj.pose.bones if not bone.parent]
        for root_bone in root_bones:
            process_bone_hierarchy(root_bone, root_displacement, kdtree, delta_positions)
        
        bpy.context.view_layer.update()


    # ------------------------------------------------------------------
    # 【追加処理：回転補正の適用】
    # 対象のdeform_bone（子が１つのみ）について、処理前と処理後の
    # 親子のHead間の方向ベクトルの変化から回転差分を求め、その回転を
    # 親ボーンに適用するとともに、子ボーンにはその影響を打ち消す補正をかける。
    # ------------------------------------------------------------------
    # for parent_name, (old_parent_head, old_child_head) in original_heads.items():
    #     parent_bone = armature_obj.pose.bones.get(parent_name)
    #     if not parent_bone or len(parent_bone.children) != 1:
    #         continue
    #     child_bone = parent_bone.children[0]

    #     # 【処理後】の親・子のHead位置を計算（ワールド座標）
    #     new_parent_head = armature_obj.matrix_world @ (parent_bone.matrix @ Vector((0, 0, 0)))
    #     new_child_head = armature_obj.matrix_world @ (child_bone.matrix @ Vector((0, 0, 0)))

    #     # 処理前と処理後の方向ベクトルを計算（子Head - 親Head）
    #     old_dir = old_child_head - old_parent_head
    #     new_dir = new_child_head - new_parent_head
    #     # もしどちらかのベクトルがゼロ長の場合はスキップ
    #     if old_dir.length == 0.001 or new_dir.length == 0.001:
    #         continue
    #     old_dir.normalize()
    #     new_dir.normalize()

    #     # 「old_dir」から「new_dir」へ回転させる回転差分を求める
    #     rot_diff = old_dir.rotation_difference(new_dir)

    #     # 親ボーンに対して、親のHeadを中心にrot_diffを適用する
    #     parent_world_matrix = armature_obj.matrix_world @ parent_bone.matrix
    #     T = Matrix.Translation(new_parent_head)
    #     T_inv = Matrix.Translation(-new_parent_head)
    #     rot_matrix = rot_diff.to_matrix().to_4x4()
    #     R = T @ rot_matrix @ T_inv
    #     new_parent_world_matrix = R @ parent_world_matrix
    #     parent_bone.matrix = armature_obj.matrix_world.inverted() @ new_parent_world_matrix

    #     # 子ボーンには、親の回転変化の影響が及ばないよう、逆の補正を適用する
    #     child_world_matrix = armature_obj.matrix_world @ child_bone.matrix
    #     compensation = T @ rot_matrix.inverted() @ T_inv
    #     new_child_world_matrix = compensation @ child_world_matrix
    #     child_bone.matrix = armature_obj.matrix_world.inverted() @ new_child_world_matrix

    #     bpy.context.view_layer.update()

    bpy.context.view_layer.update()
    
    # オブジェクトモードに戻る
    bpy.ops.object.mode_set(mode='OBJECT')

# Merged from create_deformation_mask.py

def create_deformation_mask(obj: bpy.types.Object, avatar_data: dict) -> None:
    """
    Create deformation mask vertex group based on avatar data.
    
    Parameters:
        obj: Mesh object to process
        avatar_data: Avatar data containing bone information
    """
    # 入力チェック
    if obj.type != 'MESH':
        print(f"[Error] {obj.name} is not a mesh object")
        return
    
    # Get bone groups from avatar data
    group_names = get_deformation_bone_groups(avatar_data)
    
    # TransferMaskという名前の頂点グループがすでに存在する場合は削除
    if "DeformationMask" in obj.vertex_groups:
        obj.vertex_groups.remove(obj.vertex_groups["DeformationMask"])
    
    # 新しい頂点グループを作成
    deformation_mask = obj.vertex_groups.new(name="DeformationMask")
    
    # 各頂点をチェック
    for vert in obj.data.vertices:
        should_add = False
        weight_sum = 0.0
        # 指定された頂点グループのウェイトをチェック
        for group_name in group_names:
            try:
                group = obj.vertex_groups[group_name]
                # その頂点のウェイト値を取得
                weight = 0
                for g in vert.groups:
                    if g.group == group.index:
                        weight = g.weight
                # ウェイトが0より大きければフラグを立てる
                if weight > 0:
                    should_add = True
                    weight_sum += weight
            except KeyError:
                # 頂点グループが存在しない場合はスキップ
                continue
        
        # フラグが立っている場合、DeformationMaskグループに頂点を追加
        if should_add:
            deformation_mask.add([vert.index], weight_sum, 'REPLACE')

# Merged from get_deformation_fields_mapping.py

def get_deformation_fields_mapping(avatar_data: dict) -> tuple:
    """
    アバターデータからBlendShapeの変形フィールドマッピングを取得する
    
    Parameters:
        avatar_data: アバターデータ
        
    Returns:
        tuple: (blendShapeFields, invertedBlendShapeFields) のマッピング辞書のタプル
    """
    blend_shape_fields = {}
    inverted_fields = {}
    
    # blendShapeFieldsから取得
    for field in avatar_data.get('blendShapeFields', []):
        label = field.get('label', '')
        if label:
            blend_shape_fields[label] = field
    
    # invertedBlendShapeFieldsから取得
    for field in avatar_data.get('invertedBlendShapeFields', []):
        label = field.get('label', '')
        if label:
            inverted_fields[label] = field
    
    return blend_shape_fields, inverted_fields

# Merged from get_deformation_field_multi_step.py

def get_deformation_field_multi_step(field_data_path: str) -> dict:
    """
    指定されたパスの多段階Deformation Field データを読み込み、KDTree を構築してキャッシュする。
    SaveAndApplyFieldAuto.pyのapply_field_data関数と同様の多段階データ処理をサポート。
    """
    global _deformation_field_cache
    multi_step_key = field_data_path + "_multi_step"
    if multi_step_key in _deformation_field_cache:
        return _deformation_field_cache[multi_step_key]
    
    # Deformation Field のデータ読み込み
    data = np.load(field_data_path, allow_pickle=True)
    
    # データ形式の確認と読み込み
    if 'all_field_points' in data:
        # 新形式：各ステップの座標が保存されている場合
        all_field_points = data['all_field_points']
        all_delta_positions = data['all_delta_positions']
        num_steps = int(data.get('num_steps', len(all_delta_positions)))
        # ミラー設定を確認（データに含まれていない場合はそのまま使用）
        enable_x_mirror = data.get('enable_x_mirror', False)
        if enable_x_mirror:
            # X軸ミラーリング：X座標が0より大きいデータを負に反転してミラーデータを追加
            mirrored_field_points = []
            mirrored_delta_positions = []
            
            for step in range(num_steps):
                field_points = all_field_points[step].copy()
                delta_positions = all_delta_positions[step].copy()
                
                if len(field_points) > 0:
                    # X座標が0より大きいデータを検索
                    x_positive_mask = field_points[:, 0] > 0.0
                    if np.any(x_positive_mask):
                        # ミラーデータを作成
                        mirror_field_points = field_points[x_positive_mask].copy()
                        mirror_delta_positions = delta_positions[x_positive_mask].copy()
                        
                        # X座標とX成分の変位を反転
                        mirror_field_points[:, 0] *= -1.0
                        mirror_delta_positions[:, 0] *= -1.0
                        
                        # 元のデータとミラーデータを結合
                        combined_field_points = np.vstack([field_points, mirror_field_points])
                        combined_delta_positions = np.vstack([delta_positions, mirror_delta_positions])
                        
                        mirrored_field_points.append(combined_field_points)
                        mirrored_delta_positions.append(combined_delta_positions)
                        
                    else:
                        mirrored_field_points.append(field_points)
                        mirrored_delta_positions.append(delta_positions)
                else:
                    mirrored_field_points.append(field_points)
                    mirrored_delta_positions.append(delta_positions)
            # ミラー適用後のデータを使用
            all_field_points = mirrored_field_points
            all_delta_positions = mirrored_delta_positions
        else:
            # ミラーが無効の場合、元のデータをそのまま使用
            for step in range(num_steps):
                pass  # 元のデータを維持
    elif 'field_points' in data and 'all_delta_positions' in data:
        # 旧形式：単一の座標セットが保存されている場合
        field_points = data['field_points']
        all_delta_positions = data['all_delta_positions']
        num_steps = int(data.get('num_steps', len(all_delta_positions)))
        
        # 旧形式の場合、すべてのステップで同じ座標を使用
        all_field_points = [field_points for _ in range(num_steps)]
    else:
        # 後方互換性のため、単一ステップのデータも処理
        field_points = data.get('field_points', data.get('delta_positions', []))
        delta_positions = data.get('delta_positions', data.get('all_delta_positions', [[]])[0] if 'all_delta_positions' in data else [])
        all_field_points = [field_points]
        all_delta_positions = [delta_positions]
        num_steps = 1
    # weightsが存在しない場合はすべて1のものを使用
    if 'weights' in data:
        field_weights = data['weights']
    else:
        field_weights = np.ones(len(all_field_points[0]) if len(all_field_points) > 0 else 0)
        
    world_matrix = Matrix(data['world_matrix'])
    world_matrix_inv = world_matrix.inverted()

    # kdtree_query_kの値を取得（存在しない場合はデフォルト値8を使用）
    k_neighbors = 8
    # if 'kdtree_query_k' in data:
    #     try:
    #         k_value = data['kdtree_query_k']
    #         k_neighbors = int(k_value)
    #         print(f"kdtree_query_k value: {k_neighbors}")
    #     except Exception as e:
    #         print(f"Warning: Could not process kdtree_query_k value: {e}")
    
    # RBFパラメータの読み込み
    rbf_epsilon = float(data.get('rbf_epsilon', 0.00001))
    
    field_info = {
        'data': data,
        'all_field_points': all_field_points,
        'all_delta_positions': all_delta_positions,
        'num_steps': num_steps,
        'field_weights': field_weights,
        'world_matrix': world_matrix,
        'world_matrix_inv': world_matrix_inv,
        'kdtree_query_k': k_neighbors,
        'rbf_epsilon': rbf_epsilon,
        'is_multi_step': num_steps > 1
    }
    _deformation_field_cache[multi_step_key] = field_info
    return field_info