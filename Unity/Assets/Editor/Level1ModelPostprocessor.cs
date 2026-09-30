using System.Collections.Generic;
using UnityEditor;
using UnityEngine;

namespace BianHe.EditorTools
{
    /// <summary>
    /// The white models come from Blender with bevels and hardened normals, so a corner vertex is
    /// split into several copies with different normals. The toon outline pushes the hull along the
    /// normal, which would tear open at every such split; here each copy also gets the angle-weighted
    /// average of the faces around its position, stored in UV3 for the outline pass.
    /// </summary>
    public class Level1ModelPostprocessor : AssetPostprocessor
    {
        const float Quantize = 1e-4f;

        public override uint GetVersion() => 2;   // 2: outline normals from the geometry

        /// <summary>The level model and the food models.</summary>
        static bool IsOurs(string path) => path.StartsWith("Assets/Art/Models/") || path.StartsWith("Assets/Resources/FoodModels/");

        void OnPreprocessModel()
        {
            if (!IsOurs(assetPath)) return;
            var importer = (ModelImporter)assetImporter;
            importer.importNormals = ModelImporterNormals.Import;
            importer.importTangents = ModelImporterTangents.None;
            importer.bakeAxisConversion = true;   // Blender is Z-up; bake the conversion into the hierarchy
            importer.importCameras = false;
            importer.importLights = false;
            importer.importAnimation = false;
            importer.animationType = ModelImporterAnimationType.None;
            importer.isReadable = false;
            importer.meshCompression = ModelImporterMeshCompression.Off;
        }

        void OnPostprocessModel(GameObject root)
        {
            if (!IsOurs(assetPath)) return;
            foreach (var mf in root.GetComponentsInChildren<MeshFilter>(true))
                BakeSmoothNormals(mf.sharedMesh);
        }

        static void BakeSmoothNormals(Mesh mesh)
        {
            if (mesh == null) return;
            var verts = mesh.vertices;
            var normals = mesh.normals;
            if (normals == null || normals.Length != verts.Length) return;
            var sum = new Dictionary<Vector3Int, Vector3>(verts.Length);
            var keys = new Vector3Int[verts.Length];
            for (int i = 0; i < verts.Length; i++)
            {
                var v = verts[i];
                keys[i] = new Vector3Int(Mathf.RoundToInt(v.x / Quantize), Mathf.RoundToInt(v.y / Quantize), Mathf.RoundToInt(v.z / Quantize));
            }
            // From the geometry, not the imported normals: those are weighted toward the biggest face
            // (Weighted Normals), which would push the hull along one face only and break the line.
            // Each triangle adds its face normal weighted by its corner angle at the vertex.
            var tris = mesh.triangles;
            for (int t = 0; t < tris.Length; t += 3)
            {
                int ia = tris[t], ib = tris[t + 1], ic = tris[t + 2];
                Vector3 a = verts[ia], b = verts[ib], c = verts[ic];
                var fn = Vector3.Cross(b - a, c - a);
                if (fn.sqrMagnitude < 1e-14f) continue;
                fn.Normalize();
                void Add(int i, Vector3 p, Vector3 q, Vector3 r)
                {
                    float ang = Vector3.Angle(q - p, r - p) * Mathf.Deg2Rad;
                    sum.TryGetValue(keys[i], out var s);
                    sum[keys[i]] = s + fn * ang;
                }
                Add(ia, a, b, c);
                Add(ib, b, c, a);
                Add(ic, c, a, b);
            }
            var smooth = new List<Vector3>(verts.Length);
            for (int i = 0; i < verts.Length; i++)
            {
                sum.TryGetValue(keys[i], out var n);
                smooth.Add(n.sqrMagnitude > 1e-8f ? n.normalized : normals[i]);
            }
            mesh.SetUVs(3, smooth);
        }
    }
}
