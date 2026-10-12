using UnityEngine;

namespace BianHe
{
    /// <summary>
    /// On the sun: where the painted light comes from, for the watercolor shaders' light steps and glints
    /// (_ShadeLightDir), while the sun itself is turned to cast the shadows: from high above, on the painted light's
    /// side, so that each shadow falls under what casts it, where the camera sees it, as a cartoon's does. The painted
    /// light comes low from behind the camera, as the art is lit; a sun from there would hide every shadow behind its
    /// thing.
    /// </summary>
    [ExecuteAlways]
    public class ShadeLight : MonoBehaviour
    {
        static readonly int ShadeLightDirId = Shader.PropertyToID("_ShadeLightDir");

        /// <summary>Towards the painted light (world).</summary>
        public Vector3 toLight = new(-0.3f, 0.52f, -0.8f);

        void OnEnable() => Apply();
        void OnValidate() => Apply();

        void Apply()
        {
            var t = toLight.normalized;
            Shader.SetGlobalVector(ShadeLightDirId, new Vector4(t.x, t.y, t.z, 1f));
        }

        /// <summary>The sun's rotation that casts shadows from `elevation` degrees up, towards `along` on the ground.</summary>
        public static Quaternion ShadowSun(Vector3 along, float elevation)
        {
            along.y = 0;
            along.Normalize();
            float e = elevation * Mathf.Deg2Rad;
            return Quaternion.LookRotation(along * Mathf.Cos(e) + Vector3.down * Mathf.Sin(e));
        }
    }
}
