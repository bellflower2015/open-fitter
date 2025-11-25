// ----------------------------------------------------------------------------
// Copyright (C) [2025] tallcat
//
// This file is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This file is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
// See the accompanying LICENSE file for more details.
// ----------------------------------------------------------------------------

using System.Collections.Generic;
using UnityEngine;
using Unity.Collections;
using Unity.Jobs;
using Unity.Mathematics;
using Unity.Burst;
using System.IO;
using Newtonsoft.Json;

[System.Serializable]
public class RBFData
{
    public float epsilon;
    public List<List<float>> centers;
    public List<List<float>> weights;
    public List<List<float>> poly_weights;
}

[ExecuteInEditMode] // エディタ上で動作することを明示
public class RBFDeformer : MonoBehaviour
{
    [Tooltip("Drag & Drop the RBF JSON file here.")]
    public TextAsset rbfDataJson;
    
    // Legacy support or internal path use
    [HideInInspector] public string jsonFilePath = "rbf_data.json";

    // ターゲット情報の定義
    [System.Serializable]
    public class TargetMeshInfo
    {
        public SkinnedMeshRenderer smr;
        public Mesh originalMesh;
        public Mesh deformedMesh;
    }

    [SerializeField] private List<TargetMeshInfo> targets = new List<TargetMeshInfo>();
    public List<TargetMeshInfo> Targets => targets;

    // Job用データ (共通)
    private NativeArray<float3> centers;
    private NativeArray<float3> weights;
    private NativeArray<float3> polyWeights;
    
    private float epsilon;

    // コンポーネント削除時やスクリプト再コンパイル時にメモリを解放
    void OnDisable()
    {
        DisposeNativeArrays();
    }

    void OnDestroy()
    {
        DisposeNativeArrays();
    }

    public void DisposeNativeArrays()
    {
        if (centers.IsCreated) centers.Dispose();
        if (weights.IsCreated) weights.Dispose();
        if (polyWeights.IsCreated) polyWeights.Dispose();
    }

    // エディタから「実行」ボタンで呼ばれる一括処理関数
    public void RunDeformationInEditor()
    {
        // 1. メッシュの準備 (子階層を含む全て)
        InitMeshes();

        // 2. データのロード
        if (!LoadRBFData()) return;

        // 3. 計算と適用
        ApplyRBFToAll();
    }

    void InitMeshes()
    {
        var smrs = GetComponentsInChildren<SkinnedMeshRenderer>(true);

        // 既存のターゲット情報を保持するためのマップ
        var existing = new Dictionary<Component, TargetMeshInfo>();
        foreach (var t in targets)
        {
            if (t.smr != null) existing[t.smr] = t;
        }

        targets.Clear();

        // SkinnedMeshRendererの処理
        foreach (var smr in smrs)
        {
            if (existing.TryGetValue(smr, out var info))
            {
                // 既存情報の引継ぎ
                if (info.deformedMesh == null)
                {
                    info.deformedMesh = CreatePreviewMesh(info.originalMesh);
                    smr.sharedMesh = info.deformedMesh;
                }
                targets.Add(info);
            }
            else
            {
                // 新規登録
                Mesh current = smr.sharedMesh;
                if (current == null) continue;

                // 既にプレビューメッシュになっている場合はスキップ（二重適用防止）
                if (current.name.EndsWith("_Preview"))
                {
                    Debug.LogWarning($"Skipping {smr.name} because it seems to be already deformed (Mesh: {current.name})");
                    continue;
                }

                info = new TargetMeshInfo { smr = smr, originalMesh = current };
                info.deformedMesh = CreatePreviewMesh(current);
                smr.sharedMesh = info.deformedMesh;
                targets.Add(info);
            }
        }
    }

    Mesh CreatePreviewMesh(Mesh original)
    {
        var m = Instantiate(original);
        m.name = original.name + "_Preview";
        m.hideFlags = HideFlags.DontSaveInEditor | HideFlags.DontSaveInBuild;
        return m;
    }

    bool LoadRBFData()
    {
        string jsonStr = "";

        if (rbfDataJson != null)
        {
            jsonStr = rbfDataJson.text;
        }
        else
        {
            // Fallback to file path logic if TextAsset is not set
            string path = Path.Combine(Application.dataPath, jsonFilePath);
            if (!File.Exists(path))
            {
                Debug.LogError("RBF Data not found. Please assign a JSON file to the 'Rbf Data Json' field.");
                return false;
            }
            jsonStr = File.ReadAllText(path);
        }

        try 
        {
            var data = JsonConvert.DeserializeObject<RBFData>(jsonStr);

            this.epsilon = data.epsilon;
            
            DisposeNativeArrays(); // 安全のためリセット

            // 軸変換: Blender (Right-Handed Z-Up) -> Unity (Left-Handed Y-Up)
            // Mapping: (-x, z, -y)
            // これはBoneDeformer.csの実装と一致させるための変更です。
            var centersArr = ConvertToUnitySpace(data.centers);
            var weightsArr = ConvertToUnitySpace(data.weights);
            var polyArr = ConvertToUnitySpace(data.poly_weights);

            // 多項式項の入力座標系の補正
            // Poly = Bias + C_x * x_in + C_y * y_in + C_z * z_in
            // Unity入力 (x_u, y_u, z_u) に対して:
            // x_in_blender = -x_u
            // y_in_blender = -z_u
            // z_in_blender = y_u
            
            // Row 0 (Bias): 変換済み (ConvertToUnitySpaceで出力座標系は変換されている)
            // Row 1 (X coeff): x_in = -x_u なので、係数を反転
            polyArr[1] = -polyArr[1];
            
            // Row 2 (Y coeff) & Row 3 (Z coeff):
            // Term Y: C_y * y_in = C_y * (-z_u) -> UnityのZ係数(Row 3)に -C_y をセット
            // Term Z: C_z * z_in = C_z * (y_u)  -> UnityのY係数(Row 2)に C_z をセット
            
            float3 oldRow2 = polyArr[2]; // C_y (converted to Unity output space)
            float3 oldRow3 = polyArr[3]; // C_z (converted to Unity output space)
            
            polyArr[2] = oldRow3;  // New Y coeff = Old Z coeff
            polyArr[3] = -oldRow2; // New Z coeff = -Old Y coeff

            centers = new NativeArray<float3>(centersArr, Allocator.Persistent);
            weights = new NativeArray<float3>(weightsArr, Allocator.Persistent);
            polyWeights = new NativeArray<float3>(polyArr, Allocator.Persistent);

            return true;
        }
        catch (System.Exception e)
        {
            Debug.LogError($"JSON Load Error: {e.Message}");
            return false;
        }
    }

    float3[] ConvertToUnitySpace(List<List<float>> list)
    {
        float3[] result = new float3[list.Count];
        for (int i = 0; i < list.Count; i++)
        {
            // Blender (x, y, z) -> Unity (-x, z, -y)
            result[i] = new float3(-list[i][0], list[i][2], -list[i][1]);
        }
        return result;
    }

    void ApplyRBFToAll()
    {
        foreach (var target in targets)
        {
            if (target.originalMesh == null || target.deformedMesh == null) continue;
            
            Transform t = target.smr.transform;
            ApplyRBF(target.originalMesh, target.deformedMesh, t);
        }
        Debug.Log($"<color=cyan>[RBF Deformer]</color> Applied to {targets.Count} meshes.");
    }

    void ApplyRBF(Mesh original, Mesh deformed, Transform targetTransform)
    {
        Vector3[] meshVerts = original.vertices;
        int vertexCount = meshVerts.Length;

        // ---------------------------------------------------------
        // 1. Base Mesh Deformation
        // ---------------------------------------------------------
        
        // Job用のNativeArray確保 (一時的)
        var originalVertices = new NativeArray<float3>(vertexCount, Allocator.TempJob);
        var deformedVertices = new NativeArray<float3>(vertexCount, Allocator.TempJob);

        // データのコピー
        for(int i=0; i<vertexCount; i++) originalVertices[i] = meshVerts[i];

        var job = new RBFDeformJob
        {
            vertices = originalVertices,
            deformedVertices = deformedVertices,
            centers = centers,
            weights = weights,
            polyWeights = polyWeights,
            epsilon = epsilon,
            localToWorld = targetTransform.localToWorldMatrix,
            inverseRotation = Quaternion.Inverse(targetTransform.rotation)
        };

        // 実行と待機
        job.Schedule(vertexCount, 64).Complete();

        // 結果の書き戻し & ベース変形後の頂点を保持 (シェイプキー計算用)
        Vector3[] deformedBaseVerts = new Vector3[vertexCount];
        for(int i=0; i<vertexCount; i++) deformedBaseVerts[i] = deformedVertices[i];

        deformed.vertices = deformedBaseVerts;
        deformed.RecalculateNormals();
        deformed.RecalculateBounds();
        
        originalVertices.Dispose();
        deformedVertices.Dispose();

        // ---------------------------------------------------------
        // 2. BlendShape Deformation
        // ---------------------------------------------------------
        // すべてのシェイプキーに対してRBF変形を適用する
        
        deformed.ClearBlendShapes();
        int shapeCount = original.blendShapeCount;

        if (shapeCount > 0)
        {
            Vector3[] deltaVerts = new Vector3[vertexCount];
            Vector3[] deltaNormals = new Vector3[vertexCount];
            Vector3[] deltaTangents = new Vector3[vertexCount];

            for (int i = 0; i < shapeCount; i++)
            {
                string shapeName = original.GetBlendShapeName(i);
                int frameCount = original.GetBlendShapeFrameCount(i);

                for (int f = 0; f < frameCount; f++)
                {
                    float frameWeight = original.GetBlendShapeFrameWeight(i, f);
                    original.GetBlendShapeFrameVertices(i, f, deltaVerts, deltaNormals, deltaTangents);

                    // シェイプキー適用後の絶対座標を作成
                    var shapeVerticesNA = new NativeArray<float3>(vertexCount, Allocator.TempJob);
                    var deformedShapeVerticesNA = new NativeArray<float3>(vertexCount, Allocator.TempJob);

                    for (int v = 0; v < vertexCount; v++)
                    {
                        shapeVerticesNA[v] = meshVerts[v] + deltaVerts[v];
                    }

                    // RBF変形を実行
                    var shapeJob = new RBFDeformJob
                    {
                        vertices = shapeVerticesNA,
                        deformedVertices = deformedShapeVerticesNA,
                        centers = centers,
                        weights = weights,
                        polyWeights = polyWeights,
                        epsilon = epsilon,
                        localToWorld = targetTransform.localToWorldMatrix,
                        inverseRotation = Quaternion.Inverse(targetTransform.rotation)
                    };
                    shapeJob.Schedule(vertexCount, 64).Complete();

                    // 新しいデルタを計算 (変形後シェイプ - 変形後ベース)
                    Vector3[] newDeltaVerts = new Vector3[vertexCount];
                    for (int v = 0; v < vertexCount; v++)
                    {
                        newDeltaVerts[v] = (Vector3)deformedShapeVerticesNA[v] - deformedBaseVerts[v];
                    }

                    // 変形されたシェイプキーを追加
                    // Note: 法線と接線のデルタはRBF変形が困難なため、元の値を維持します。
                    // 大きな変形の場合、法線が正しくない可能性がありますが、形状は維持されます。
                    deformed.AddBlendShapeFrame(shapeName, frameWeight, newDeltaVerts, deltaNormals, deltaTangents);

                    shapeVerticesNA.Dispose();
                    deformedShapeVerticesNA.Dispose();
                }
            }
            Debug.Log($"<color=cyan>[RBF Deformer]</color> Processed {shapeCount} BlendShapes for {original.name}");
        }
    }

    [BurstCompile]
    struct RBFDeformJob : IJobParallelFor
    {
        [ReadOnly] public NativeArray<float3> vertices;
        [ReadOnly] public NativeArray<float3> centers;
        [ReadOnly] public NativeArray<float3> weights;
        [ReadOnly] public NativeArray<float3> polyWeights;
        [ReadOnly] public float epsilon;
        [ReadOnly] public float4x4 localToWorld;
        [ReadOnly] public quaternion inverseRotation;

        [WriteOnly] public NativeArray<float3> deformedVertices;

        public void Execute(int i)
        {
            float3 p_local = vertices[i];
            float3 p_world = math.transform(localToWorld, p_local);
            float3 displacement = float3.zero;
            float eps2 = epsilon * epsilon;

            for (int j = 0; j < centers.Length; j++)
            {
                float distSq = math.distancesq(p_world, centers[j]);
                float phi = math.sqrt(distSq + eps2);
                displacement += weights[j] * phi;
            }

            displacement += polyWeights[0];
            displacement += polyWeights[1] * p_world.x;
            displacement += polyWeights[2] * p_world.y;
            displacement += polyWeights[3] * p_world.z;

            float3 disp_local = math.rotate(inverseRotation, displacement);
            deformedVertices[i] = p_local + disp_local;
        }
    }
}