import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from algo_utils.search_utils import (
    find_best_matching_target_settings,
)
from algo_utils.get_blendshape_groups import get_blendshape_groups
from blender_utils.process_single_blendshape_transition_set import (
    process_single_blendshape_transition_set,
)
from io_utils.avatar_data import load_avatar_data_for_blendshape_analysis
from misc_utils.get_deformation_fields_mapping import get_deformation_fields_mapping


def process_blendshape_transitions(current_config: dict, next_config: dict) -> None:
    """
    連続する2つのConfigファイル間のBlendShape設定の差異を検出し、遷移データを作成する
    
    Parameters:
        current_config: 前のConfigファイルの設定
        next_config: 後のConfigファイルの設定
    """
    try:
        blendshape_settings = next_config['config_data'].get('sourceBlendShapeSettings', [])
        current_config['next_blendshape_settings'] = blendshape_settings
        
        # 前のConfigのbaseAvatarDataPathからアバターデータを読み込み
        current_base_avatar_data = load_avatar_data_for_blendshape_analysis(current_config['base_avatar_data'])
        
        # BlendShapeGroupsとDeformationFieldsを取得
        blend_shape_groups = get_blendshape_groups(current_base_avatar_data)
        blend_shape_fields, inverted_blend_shape_fields = get_deformation_fields_mapping(current_base_avatar_data)
        
        # 設定ファイルのディレクトリを取得
        current_config_dir = os.path.dirname(os.path.abspath(current_config['config_path']))
        
        print(f"Processing BlendShape transitions between {os.path.basename(current_config['config_path'])} and {os.path.basename(next_config['config_path'])}")
        
        all_transition_sets = []
        all_default_transition_sets = []
        
        # 1. ルートレベルの処理
        # 全てのtargetBlendShapeSettingsを収集
        all_target_settings = {}
        all_target_mask_bones = {}
        
        # ルートレベルのtargetBlendShapeSettings
        current_target_settings = current_config['config_data'].get('targetBlendShapeSettings', [])
        all_target_settings['Basis'] = current_target_settings
        all_target_mask_bones['Basis'] = None
        
        # blendShapeFields内のtargetBlendShapeSettings
        current_blend_shape_fields = current_config['config_data'].get('blendShapeFields', [])
        for field in current_blend_shape_fields:
            field_label = field.get('label', '')
            field_target_settings = field.get('targetBlendShapeSettings', [])
            all_target_settings[field_label] = field_target_settings
            all_target_mask_bones[field_label] = field.get('maskBones', [])
        
        # next_configのsourceBlendShapeSettingsに最も近いtargetBlendShapeSettingsを見つける
        next_source_settings = next_config['config_data'].get('sourceBlendShapeSettings', [])
        if all_target_settings:
            best_label, best_target_settings = find_best_matching_target_settings(
                'Basis', all_target_settings, all_target_mask_bones, next_source_settings, blend_shape_fields, current_config_dir, None
            )
            
            print(f"  Best matching target for root level: '{best_label}'")
            
            # 最適なtargetBlendShapeSettingsとsourceBlendShapeSettingsの遷移を作成
            basis_transitions = process_single_blendshape_transition_set(
                best_target_settings, next_source_settings, 'Basis', best_label,
                blend_shape_groups, blend_shape_fields, inverted_blend_shape_fields,
                current_config_dir
            )
            all_transition_sets.append(basis_transitions)

            basis_default_transitions = process_single_blendshape_transition_set(
                all_target_settings['Basis'], next_source_settings, 'Basis', 'Basis',
                blend_shape_groups, blend_shape_fields, inverted_blend_shape_fields,
                current_config_dir
            )
            all_default_transition_sets.append(basis_default_transitions)
        
        # 2. blendShapeFields内の処理
        next_blend_shape_fields = next_config['config_data'].get('blendShapeFields', [])
        
        for next_field in next_blend_shape_fields:
            next_field_source_label = next_field.get('sourceLabel', '')
            next_field_source_settings = next_field.get('sourceBlendShapeSettings', [])
            next_field_mask_bones = next_field.get('maskBones', [])
            
            if all_target_settings:
                # 最適なtargetBlendShapeSettingsを見つける
                best_label, best_target_settings = find_best_matching_target_settings(
                    next_field_source_label, all_target_settings, all_target_mask_bones, next_field_source_settings, blend_shape_fields, current_config_dir, next_field_mask_bones
                )
                
                print(f"  Best matching target for field '{next_field_source_label}': '{best_label}'")
                
                # 遷移を作成
                field_transitions = process_single_blendshape_transition_set(
                    best_target_settings, next_field_source_settings, next_field_source_label, best_label,
                    blend_shape_groups, blend_shape_fields, inverted_blend_shape_fields,
                    current_config_dir, 
                    next_field_mask_bones
                )
                all_transition_sets.append(field_transitions)

                default_target_setting = None
                if next_field_source_label in all_target_settings.keys():
                    default_target_setting = all_target_settings[next_field_source_label]
                if default_target_setting is not None:
                    field_default_transitions = process_single_blendshape_transition_set(
                        default_target_setting, next_field_source_settings, next_field_source_label, next_field_source_label,
                        blend_shape_groups, blend_shape_fields, inverted_blend_shape_fields,
                        current_config_dir,
                        next_field_mask_bones
                    )
                    all_default_transition_sets.append(field_default_transitions)
        
        # 遷移データを次のconfigオブジェクトに挿入
        current_config['config_data']['blend_shape_transition_sets'] = all_transition_sets
        current_config['config_data']['blend_shape_default_transition_sets'] = all_default_transition_sets
        
        print(f"  Total transition sets: {len(all_transition_sets)}")
        print(f"  Total default transition sets: {len(all_default_transition_sets)}")
        
    except Exception as e:
        print(f"Error processing BlendShape transitions: {e}")
        import traceback
        traceback.print_exc()
