using System.Collections.Generic;
using UnityEngine;
using System.Linq;
using Newtonsoft.Json;
using System.IO;

// JSONデータの構造に合わせてC#クラスを定義
[System.Serializable]
public class BoneTransformData
{
    public List<float> location;
    public List<float> rotation;
    public List<float> scale;
    public List<float> head_world;
    public List<float> head_world_transformed;
    public List<List<float>> delta_matrix;
}

public class BoneDeformer : MonoBehaviour
{
    // UnityエディタからJSONファイルをアタッチする
    public TextAsset poseDataJson;
    public string jsonFilePath; // Optional: Path to JSON if not using TextAsset

    // 変形対象のモデルのルートTransform
    public Transform rootTransform;

    public enum BoneAxis
    {
        Y_Axis, // Standard Blender Bone (Y is Length)
        Z_Axis, // Common Unity Rig (Z is Length)
        X_Axis  // Rare but possible
    }

    [Tooltip("The axis of the bone that corresponds to the length (Blender Y).")]
    public BoneAxis boneLengthAxis = BoneAxis.Y_Axis;

    // For caching Unity's initial pose
    private Dictionary<string, Transform> boneMap;
    
    private class InitialBoneState
    {
        public Vector3 localPosition;
        public Quaternion localRotation;
        public Vector3 localScale;
        
        public Vector3 worldPosition;
        public Quaternion worldRotation;
        public Vector3 lossyScale;
    }
    private Dictionary<string, InitialBoneState> initialStates;
    private bool isInitialized = false;

    // Blender World Space (Right Handed, Z-Up) -> Unity World Space (Left Handed, Y-Up)
    // Mapping: (x, z, -y)
    // Blender X (Right) -> Unity X (Right)
    // Blender Y (Back) -> Unity -Z (Back)
    // Blender Z (Up) -> Unity Y (Up)
    private Vector3 ConvertWorldVector(List<float> vec)
    {
        return new Vector3(vec[0], vec[2], -vec[1]);
    }

    // Blenderのボーンの回転(Euler XYZ Degrees)をUnityの回転に変換
    private Quaternion ConvertRotation(List<float> rot)
    {
        // Input is Blender Euler XYZ (Degrees).
        // Construct Blender Quaternion (Intrinsic XYZ -> Z * Y * X).
        float x = rot[0];
        float y = rot[1];
        float z = rot[2];

        Quaternion qx = Quaternion.AngleAxis(x, Vector3.right);
        Quaternion qy = Quaternion.AngleAxis(y, Vector3.up);
        Quaternion qz = Quaternion.AngleAxis(z, Vector3.forward);
        
        Quaternion qBlender = qz * qy * qx;

        // Convert Blender Quaternion (RH, Z-Up) to Unity Quaternion (LH, Y-Up).
        // Mapping:
        // 1. Neck (Blender Z axis) Left (+Z) -> Unity Left (-Y). So qUnity.y = -qBlender.z
        // 2. Bend (Blender X axis) Forward (+X) -> Unity Forward (+X). So qUnity.x = qBlender.x
        // 3. Legs (Blender Y axis) Sideways (+Y) -> Unity Sideways (+Z). So qUnity.z = qBlender.y
        //    (User reported previous y -> -z was reversed, so we flip to y -> z)
        
        // Mapping: (x, -z, y, w)
        return new Quaternion(qBlender.x, -qBlender.z, qBlender.y, qBlender.w);
    }
    
    private Vector3 ConvertScale(List<float> s)
    {
        // Input is Blender World Scale Factors (sx, sy, sz).
        // Map to Unity World Axes.
        // Blender X (sx) -> Unity X (magnitude is same)
        // Blender Y (sy) -> Unity Z
        // Blender Z (sz) -> Unity Y
        
        return new Vector3(s[0], s[2], s[1]);
    }

    private void InitializeBoneMap()
    {
        if (rootTransform == null) rootTransform = transform;
        boneMap = new Dictionary<string, Transform>();
        initialStates = new Dictionary<string, InitialBoneState>();
        MapBonesRecursive(rootTransform);
        isInitialized = true;
    }

    private void MapBonesRecursive(Transform t)
    {
        if (!boneMap.ContainsKey(t.name))
        {
            boneMap.Add(t.name, t);
            initialStates.Add(t.name, new InitialBoneState
            {
                localPosition = t.localPosition,
                localRotation = t.localRotation,
                localScale = t.localScale,
                worldPosition = t.position,
                worldRotation = t.rotation,
                lossyScale = t.lossyScale
            });
        }
        
        foreach (Transform child in t)
        {
            MapBonesRecursive(child);
        }
    }

    /// <summary>
    /// ポーズをモデルに適用する
    /// </summary>
    public void ApplyPose()
    {
        if (!isInitialized || boneMap == null) InitializeBoneMap();

        string jsonContent = "";
        if (poseDataJson != null)
        {
            jsonContent = poseDataJson.text;
        }
        else if (!string.IsNullOrEmpty(jsonFilePath) && File.Exists(jsonFilePath))
        {
            jsonContent = File.ReadAllText(jsonFilePath);
        }
        else
        {
            Debug.LogError("No JSON data provided.");
            return;
        }

        var poseData = JsonConvert.DeserializeObject<Dictionary<string, BoneTransformData>>(jsonContent);

        // Apply in order of hierarchy? 
        // Since we are setting World Position, order might not matter for Position,
        // but for Scale (which depends on parent), we should ideally go from root down.
        // However, the dictionary order is not guaranteed.
        // But since we calculate Local Scale based on Parent's *current* Lossy Scale,
        // we MUST process parents before children.
        
        // Sort keys by hierarchy depth? Or just traverse our boneMap recursively.
        ApplyPoseRecursive(rootTransform, poseData);
        
        Debug.Log("Pose applied.");
    }

    private void ApplyPoseRecursive(Transform t, Dictionary<string, BoneTransformData> poseData)
    {
        string boneName = t.name;
        // Handle prefix stripping if needed
        // (Simple check: if key exists directly, use it. If not, check if any key ends with :name)
        string key = boneName;
        if (!poseData.ContainsKey(key))
        {
            // Try to find a key that ends with ":" + boneName
            var match = poseData.Keys.FirstOrDefault(k => k.EndsWith(":" + boneName));
            if (match != null) key = match;
        }

        if (poseData.ContainsKey(key))
        {
            ApplyTransformToBone(t, poseData[key]);
        }

        foreach (Transform child in t)
        {
            ApplyPoseRecursive(child, poseData);
        }
    }

    private Transform FindBone(string name)
    {
        if (boneMap.ContainsKey(name)) return boneMap[name];
        return null;
    }

    private void ApplyTransformToBone(Transform bone, BoneTransformData data)
    {
        if (!initialStates.ContainsKey(bone.name)) return;
        InitialBoneState init = initialStates[bone.name];

        // 1. Position
        // Use head_world_transformed from JSON.
        // This is the absolute world position in Blender.
        // Convert to Unity World Space.
        if (data.head_world_transformed != null)
        {
            Vector3 targetWorldPos = ConvertWorldVector(data.head_world_transformed);
            
            // The JSON head_world_transformed is the position of the Head.
            // In Unity, transform.position corresponds to the Head (pivot).
            // However, we need to align the coordinate systems.
            // If the model was imported with some offset or scaling, direct mapping might be off.
            // But let's assume 1:1 mapping for now as per "OpenFitter" nature.
            
            // Wait, if the Unity model is scaled or offset at the root, absolute coordinates might be wrong.
            // Better approach: Calculate the Delta Vector in World Space and add to Initial World Position.
            // JSON 'location' = head_world_transformed - head_world (in Blender).
            // So Target = Initial + Delta.
            
            Vector3 worldDelta = ConvertWorldVector(data.location);
            bone.position = init.worldPosition + worldDelta;
        }

        // 2. Rotation
        // data.rotation is Euler angles of the Delta Matrix (World Space Delta).
        // R_target = R_delta * R_initial
        Quaternion deltaRot = ConvertRotation(data.rotation);
        bone.rotation = deltaRot * init.worldRotation; // Order: Apply delta to the initial orientation?
        // Or init * delta?
        // If delta is "change in world space", then R_new = Delta * R_old.
        // Let's try Delta * Init.

        // 3. Scale
        // data.scale is the Scale of the Delta Matrix (Accumulated Scale Factor).
        // S_target_world = S_initial_world * S_delta.
        Vector3 deltaScale = ConvertScale(data.scale);
        Vector3 targetLossyScale = Vector3.Scale(init.lossyScale, deltaScale);
        
        // Calculate required Local Scale to achieve Target Lossy Scale.
        // localScale = targetLossyScale / parentLossyScale
        if (bone.parent != null)
        {
            Vector3 parentLossy = bone.parent.lossyScale;
            // Avoid divide by zero
            float x = (parentLossy.x != 0) ? targetLossyScale.x / parentLossy.x : 1;
            float y = (parentLossy.y != 0) ? targetLossyScale.y / parentLossy.y : 1;
            float z = (parentLossy.z != 0) ? targetLossyScale.z / parentLossy.z : 1;
            bone.localScale = new Vector3(x, y, z);
        }
        else
        {
            bone.localScale = targetLossyScale;
        }
    }
    
    public void ResetPose()
    {
        if (!isInitialized) return;
        foreach(var kvp in initialStates)
        {
            Transform t = boneMap[kvp.Key];
            if(t != null)
            {
                t.localPosition = kvp.Value.localPosition;
                t.localRotation = kvp.Value.localRotation;
                t.localScale = kvp.Value.localScale;
            }
        }
    }
}
