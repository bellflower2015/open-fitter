import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import argparse
import json

from mathutils import Vector
from process_blendshape_transitions import process_blendshape_transitions


def parse_args():
    parser = argparse.ArgumentParser()
    
    # 既存の引数
    parser.add_argument('--input', required=True, help='Input clothing FBX file path')
    parser.add_argument('--output', required=True, help='Output FBX file path')
    parser.add_argument('--base', required=True, help='Base Blender file path')
    parser.add_argument('--base-fbx', required=True, help='Comma-separated list of base avatar FBX file paths')
    parser.add_argument('--config', required=True, help='Comma-separated list of config file paths')
    parser.add_argument('--hips-position', type=str, help='Target Hips bone world position (x,y,z format)')
    parser.add_argument('--blend-shapes', type=str, help='Comma-separated list of blend shape labels to apply')
    parser.add_argument('--cloth-metadata', type=str, help='Path to cloth metadata JSON file')
    parser.add_argument('--mesh-material-data', type=str, help='Path to mesh material data JSON file')
    parser.add_argument('--init-pose', required=True, help='Initial pose data JSON file path')
    parser.add_argument('--target-meshes', required=False, help='Comma-separated list of mesh names to process')
    parser.add_argument('--no-subdivision', action='store_true', help='Disable subdivision during DeformationField deformation')
    parser.add_argument('--no-triangle', action='store_true', help='Disable mesh triangulation')
    parser.add_argument('--blend-shape-values', type=str, help='Comma-separated list of float values for blend shape intensities')
    parser.add_argument('--blend-shape-mappings', type=str, help='Semicolon-separated mappings of label,customName pairs')
    parser.add_argument('--name-conv', type=str, help='Path to bone name conversion JSON file')
    parser.add_argument('--mesh-renderers', type=str, help='Semicolon-separated list of meshObject,parentObject pairs')
    
    print(sys.argv)

    # Get all args after "--"
    argv = sys.argv
    if "--" not in argv:
        parser.print_help()
        sys.exit(1)
        
    args = parser.parse_args(argv[argv.index("--") + 1:])
    
    # Parse comma-separated base-fbx and config paths
    base_fbx_paths = [path.strip() for path in args.base_fbx.split(',')]
    config_paths = [path.strip() for path in args.config.split(',')]
    
    # Validate that base-fbx and config have the same number of entries
    if len(base_fbx_paths) != len(config_paths):
        print(f"Error: Number of base-fbx files ({len(base_fbx_paths)}) must match number of config files ({len(config_paths)})")
        sys.exit(1)
    
    # Validate basic file paths
    required_paths = [
        args.input, args.base, 
        args.init_pose
    ]
    for path in required_paths:
        if not os.path.exists(path):
            sys.exit(1)
    
    # Validate all base-fbx files exist
    for path in base_fbx_paths:
        if not os.path.exists(path):
            sys.exit(1)
    
    # Validate all config files exist
    for path in config_paths:
        if not os.path.exists(path):
            sys.exit(1)
    
    # Process each config file and create configuration pairs
    config_pairs = []
    for i, (base_fbx_path, config_path) in enumerate(zip(base_fbx_paths, config_paths)):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # blendShapeFieldsの重複するlabelとsourceLabelに___idを付加
            if 'blendShapeFields' in config_data:
                blend_shape_fields = config_data['blendShapeFields']
                
                # labelの重複をチェックして___idを付加
                label_counts = {}
                for field in blend_shape_fields:
                    label = field.get('label', '')
                    if label:
                        label_counts[label] = label_counts.get(label, 0) + 1
                
                label_ids = {}
                for field in blend_shape_fields:
                    label = field.get('label', '')
                    if label and label_counts[label] > 1:
                        current_id = label_ids.get(label, 0)
                        field['label'] = f"{label}___{current_id}"
                        label_ids[label] = current_id + 1
                
                # sourceLabelの重複をチェックして___idを付加
                source_label_counts = {}
                for field in blend_shape_fields:
                    source_label = field.get('sourceLabel', '')
                    if source_label:
                        source_label_counts[source_label] = source_label_counts.get(source_label, 0) + 1
                
                source_label_ids = {}
                for field in blend_shape_fields:
                    source_label = field.get('sourceLabel', '')
                    if source_label and source_label_counts[source_label] > 1:
                        current_id = source_label_ids.get(source_label, 0)
                        field['sourceLabel'] = f"{source_label}___{current_id}"
                        source_label_ids[source_label] = current_id + 1
            
            # Get config file directory
            config_dir = os.path.dirname(os.path.abspath(config_path))
            
            # Extract and resolve avatar data paths
            pose_data_path = config_data.get('poseDataPath')
            field_data_path = config_data.get('fieldDataPath')
            base_avatar_data_path = config_data.get('baseAvatarDataPath')
            clothing_avatar_data_path = config_data.get('clothingAvatarDataPath')
            
            if not pose_data_path:
                sys.exit(1)
            if not field_data_path:
                sys.exit(1)
            if not base_avatar_data_path:
                sys.exit(1)
            if not clothing_avatar_data_path:
                sys.exit(1)
            
            # Convert relative paths to absolute paths
            if not os.path.isabs(pose_data_path):
                pose_data_path = os.path.join(config_dir, pose_data_path)
            if not os.path.isabs(field_data_path):
                field_data_path = os.path.join(config_dir, field_data_path)
            if not os.path.isabs(base_avatar_data_path):
                base_avatar_data_path = os.path.join(config_dir, base_avatar_data_path)
            if not os.path.isabs(clothing_avatar_data_path):
                clothing_avatar_data_path = os.path.join(config_dir, clothing_avatar_data_path)
            
            # Validate avatar data paths
            if not os.path.exists(pose_data_path):
                print(f"Error: Pose data file not found: {pose_data_path} (from config {config_path})")
                sys.exit(1)
            if not os.path.exists(field_data_path):
                print(f"Error: Field data file not found: {field_data_path} (from config {config_path})")
                sys.exit(1)
            if not os.path.exists(base_avatar_data_path):
                print(f"Error: Base avatar data file not found: {base_avatar_data_path} (from config {config_path})")
                sys.exit(1)
            if not os.path.exists(clothing_avatar_data_path):
                print(f"Error: Clothing avatar data file not found: {clothing_avatar_data_path} (from config {config_path})")
                sys.exit(1)
            
            hips_position = None
            target_meshes = None
            init_pose = None
            blend_shapes = None
            blend_shape_values = None
            blend_shape_mappings = None
            mesh_renderers = None
            input_clothing_fbx_path = args.output;
            if i == 0:
                if args.hips_position:
                    x, y, z = map(float, args.hips_position.split(','))
                    hips_position = Vector((x, y, z))
                target_meshes = args.target_meshes;
                init_pose = args.init_pose;
                blend_shapes = args.blend_shapes;
                # Parse blend shape values if provided
                if args.blend_shape_values:
                    try:
                        blend_shape_values = [float(v.strip()) for v in args.blend_shape_values.split(',')]
                    except ValueError as e:
                        sys.exit(1)
                # Parse blend shape mappings if provided
                if args.blend_shape_mappings:
                    try:
                        blend_shape_mappings = {}
                        pairs = args.blend_shape_mappings.split(';')
                        for pair in pairs:
                            if pair.strip():
                                label, custom_name = pair.split(',', 1)
                                blend_shape_mappings[label.strip()] = custom_name.strip()
                    except ValueError as e:
                        sys.exit(1)
                # Parse mesh renderers if provided
                if args.mesh_renderers:
                    try:
                        mesh_renderers = {}
                        pairs = args.mesh_renderers.split(';')
                        for pair in pairs:
                            if pair.strip():
                                mesh_name, parent_name = pair.split(':', 1)
                                mesh_renderers[mesh_name.strip()] = parent_name.strip()
                    except ValueError as e:
                        sys.exit(1)
                input_clothing_fbx_path = args.input;
            
            skip_blend_shape_generation = True;
            if i == len(config_paths) - 1:
                skip_blend_shape_generation = False;

            do_not_use_base_pose = config_data.get('doNotUseBasePose', 0);
            
            # Create configuration pair
            config_pair = {
                'base_fbx': base_fbx_path,
                'config_path': config_path,
                'config_data': config_data,
                'pose_data': pose_data_path,
                'field_data': field_data_path,
                'base_avatar_data': base_avatar_data_path,
                'clothing_avatar_data': clothing_avatar_data_path,
                'hips_position': hips_position,
                'target_meshes': target_meshes,
                'init_pose': init_pose,
                'blend_shapes': blend_shapes,
                'blend_shape_values': blend_shape_values,
                'blend_shape_mappings': blend_shape_mappings,
                'mesh_renderers': mesh_renderers,
                'input_clothing_fbx_path': input_clothing_fbx_path,
                'skip_blend_shape_generation': skip_blend_shape_generation,
                'do_not_use_base_pose': do_not_use_base_pose
            }
            config_pairs.append(config_pair)
            
        except json.JSONDecodeError as e:
            sys.exit(1)
        except Exception as e:
            sys.exit(1)
    
    # Process BlendShape transitions for consecutive config pairs
    if len(config_pairs) >= 2:
        for i in range(len(config_pairs) - 1):
            process_blendshape_transitions(config_pairs[i], config_pairs[i + 1])
        config_pairs[len(config_pairs) - 1]['next_blendshape_settings'] = config_pairs[len(config_pairs) - 1]['config_data'].get('targetBlendShapeSettings', [])
    
    # 中間pairではbase_fbxを使用しない（最終pairでのみターゲットアバターFBXをロード）
    # Template.fbx依存を排除するため、中間pairのbase_fbxをNoneに設定
    if len(config_pairs) >= 2:
        for i in range(len(config_pairs) - 1):
            config_pairs[i]['base_fbx'] = None
    
    # Store configuration pairs in args for later use (後方互換性)
    args.config_pairs = config_pairs
            
    # Parse hips position if provided
    if args.hips_position:
        try:
            x, y, z = map(float, args.hips_position.split(','))
            args.hips_position = Vector((x, y, z))
        except:
            print("Error: Invalid hips position format. Use x,y,z")
            sys.exit(1)
    
    # 新アーキテクチャ: (args, config_pairs)を返す
    return args, config_pairs
