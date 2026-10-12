using System;
using System.Collections.Generic;
using UnityEngine;

namespace BianHe
{
    /// <summary>
    /// Fitting the 3D food where it goes, from its vertices (the food models are imported readable): how much room
    /// it takes on the ground (the middle of it, how far it reaches from there, its lowest point), scaled down to fit
    /// a box (a tray, a cell of the board, a place on the table) resting on its floor, or bent into a bowl (the wok)
    /// so that nothing goes through what it sits on.
    /// </summary>
    public static class FoodFit
    {
        /// <summary>Where `go` stands on the ground: the middle of its outline seen from above, how far it reaches from
        /// there (the farthest vertex), its half-widths along x and z, and its lowest point (world).</summary>
        public static (Vector3 middle, float reach, Vector2 half, float bottom) Footprint(GameObject go)
        {
            float x0 = float.MaxValue, x1 = float.MinValue, z0 = float.MaxValue, z1 = float.MinValue, y0 = float.MaxValue;
            var filters = go.GetComponentsInChildren<MeshFilter>();
            foreach (var mf in filters)
            {
                if (mf.sharedMesh == null || !mf.sharedMesh.isReadable) continue;
                var m = mf.transform.localToWorldMatrix;
                foreach (var v in mf.sharedMesh.vertices)
                {
                    var w = m.MultiplyPoint3x4(v);
                    if (w.x < x0) x0 = w.x;
                    if (w.x > x1) x1 = w.x;
                    if (w.z < z0) z0 = w.z;
                    if (w.z > z1) z1 = w.z;
                    if (w.y < y0) y0 = w.y;
                }
            }
            if (x0 > x1)   // nothing readable: the renderers' boxes
            {
                var b = Bounds(go);
                return (new Vector3(b.center.x, b.min.y, b.center.z), Mathf.Max(b.extents.x, b.extents.z),
                        new Vector2(b.extents.x, b.extents.z), b.min.y);
            }
            var mid = new Vector3((x0 + x1) / 2, y0, (z0 + z1) / 2);
            float reach = 0;
            foreach (var mf in filters)
            {
                if (mf.sharedMesh == null || !mf.sharedMesh.isReadable) continue;
                var m = mf.transform.localToWorldMatrix;
                foreach (var v in mf.sharedMesh.vertices)
                {
                    var w = m.MultiplyPoint3x4(v);
                    float r = new Vector2(w.x - mid.x, w.z - mid.z).sqrMagnitude;
                    if (r > reach) reach = r;
                }
            }
            return (mid, Mathf.Sqrt(reach), new Vector2((x1 - x0) / 2, (z1 - z0) / 2), y0);
        }

        /// <summary>The outline of `go` seen from above: the convex hull of its vertices on the ground (world x, z).</summary>
        public static List<Vector2> Hull(GameObject go)
        {
            var pts = new List<Vector2>();
            foreach (var mf in go.GetComponentsInChildren<MeshFilter>())
            {
                if (mf.sharedMesh == null || !mf.sharedMesh.isReadable) continue;
                var m = mf.transform.localToWorldMatrix;
                var verts = mf.sharedMesh.vertices;
                int step = Mathf.Max(1, verts.Length / 1500);   // enough for its outline
                for (int i = 0; i < verts.Length; i += step)
                {
                    var w = m.MultiplyPoint3x4(verts[i]);
                    pts.Add(new Vector2(w.x, w.z));
                }
            }
            if (pts.Count < 3)
            {
                var b = Bounds(go);
                return new List<Vector2> { new(b.min.x, b.min.z), new(b.max.x, b.min.z), new(b.max.x, b.max.z), new(b.min.x, b.max.z) };
            }
            pts.Sort((a, b) => a.x != b.x ? a.x.CompareTo(b.x) : a.y.CompareTo(b.y));
            float Cross(Vector2 o, Vector2 a, Vector2 b) => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
            var hull = new List<Vector2>();
            for (int pass = 0; pass < 2; pass++)   // the lower then the upper chain (monotone chain)
            {
                int start = hull.Count;
                for (int k = 0; k < pts.Count; k++)
                {
                    var p = pass == 0 ? pts[k] : pts[pts.Count - 1 - k];
                    while (hull.Count >= start + 2 && Cross(hull[hull.Count - 2], hull[hull.Count - 1], p) <= 0) hull.RemoveAt(hull.Count - 1);
                    hull.Add(p);
                }
                hull.RemoveAt(hull.Count - 1);
            }
            return hull;
        }

        /// <summary>Whether two outlines from Hull overlap, closer than `gap` (separating axes).</summary>
        public static bool Overlap(List<Vector2> a, List<Vector2> b, float gap = 0f)
        {
            foreach (var poly in new[] { a, b })
                for (int i = 0; i < poly.Count; i++)
                {
                    var e = poly[(i + 1) % poly.Count] - poly[i];
                    var n = new Vector2(-e.y, e.x).normalized;
                    float a0 = float.MaxValue, a1 = float.MinValue, b0 = float.MaxValue, b1 = float.MinValue;
                    foreach (var p in a) { float d = Vector2.Dot(n, p); a0 = Mathf.Min(a0, d); a1 = Mathf.Max(a1, d); }
                    foreach (var p in b) { float d = Vector2.Dot(n, p); b0 = Mathf.Min(b0, d); b1 = Mathf.Max(b1, d); }
                    if (a1 + gap <= b0 || b1 + gap <= a0) return false;   // a gap along this axis: apart
                }
            return true;
        }

        public static Bounds Bounds(GameObject go)
        {
            var rs = go.GetComponentsInChildren<Renderer>();
            if (rs.Length == 0) return new Bounds(go.transform.position, Vector3.zero);
            var b = rs[0].bounds;
            foreach (var r in rs) b.Encapsulate(r.bounds);
            return b;
        }

        /// <summary>`go` scaled so that it fits inside `room` (a box on the ground: its floor is room's bottom): down
        /// if it is bigger, up to fill it if it is smaller, by at most `grow` times (1: never up), its middle over
        /// room's middle and its lowest point on the floor, `lift` above it.</summary>
        public static void FitIn(GameObject go, Bounds room, float lift = 0.002f, float grow = 1f)
        {
            var f = Footprint(go);
            float k = Mathf.Min(grow, room.extents.x / Mathf.Max(f.half.x, 1e-4f), room.extents.z / Mathf.Max(f.half.y, 1e-4f));
            if (k != 1f) ScaleAbout(go, f.middle, k);
            f = Footprint(go);
            go.transform.position += new Vector3(room.center.x - f.middle.x, room.min.y + lift - f.bottom, room.center.z - f.middle.z);
        }

        /// <summary>`go` scaled by k about a point (its scale and its position both).</summary>
        public static void ScaleAbout(GameObject go, Vector3 about, float k)
        {
            var t = go.transform;
            t.localScale *= k;
            t.position = about + (t.position - about) * k;
        }

        /// <summary>
        /// Bends `go` into a bowl: every vertex raised by how high the bowl's inside is under it, height(distance from
        /// the bowl's axis), so that food laid out flat on the bowl's bottom follows its curve up the sides instead of
        /// going through them. The meshes are copied first (the shared ones stay as they are).
        /// </summary>
        public static void BendInto(GameObject go, Vector3 axis, Func<float, float> height)
        {
            foreach (var mf in go.GetComponentsInChildren<MeshFilter>())
            {
                var src = mf.sharedMesh;
                if (src == null || !src.isReadable) continue;
                var mesh = UnityEngine.Object.Instantiate(src);
                mesh.name = src.name + " (bent)";
                var toWorld = mf.transform.localToWorldMatrix;
                var toLocal = mf.transform.worldToLocalMatrix;
                var verts = mesh.vertices;
                for (int i = 0; i < verts.Length; i++)
                {
                    var w = toWorld.MultiplyPoint3x4(verts[i]);
                    w.y += height(new Vector2(w.x - axis.x, w.z - axis.z).magnitude);
                    verts[i] = toLocal.MultiplyPoint3x4(w);
                }
                mesh.vertices = verts;
                mesh.RecalculateBounds();
                mf.sharedMesh = mesh;
            }
        }
    }
}
