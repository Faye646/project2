using UnityEditor;
using UnityEngine;

namespace BianHe.EditorTools
{
    /// <summary>
    /// Food and seasoning art (Resources/Food), the baked 三渲二 food images (Resources/Food3D) and the
    /// kitchen backdrop layers (Resources/UI) import as UI sprites.
    /// </summary>
    public class FoodSpritePostprocessor : AssetPostprocessor
    {
        void OnPreprocessTexture()
        {
            if (assetPath.StartsWith("Assets/Art/Textures/"))   // painted patches for WatercolorLit: tile mirrored
            {
                var t = (TextureImporter)assetImporter;
                t.textureType = TextureImporterType.Default;
                // the meat's detail textures (food_textures.py) are seamless data, R pattern and G height:
                // repeated, linear, and kept as uncompressed RG so the bump has no block steps
                bool detail = System.IO.Path.GetFileName(assetPath).StartsWith("food_");
                t.wrapMode = detail ? TextureWrapMode.Repeat : TextureWrapMode.Mirror;
                t.sRGBTexture = !detail && !assetPath.EndsWith("wc_noise.png");
                t.mipmapEnabled = true;
                t.maxTextureSize = detail ? 512 : 1024;
                if (detail)
                {
                    t.filterMode = FilterMode.Trilinear;
                    foreach (var platform in new[] { "Standalone", "Android", "iPhone", "WebGL" })
                        t.SetPlatformTextureSettings(new TextureImporterPlatformSettings
                        {
                            name = platform, overridden = true, maxTextureSize = 512, format = TextureImporterFormat.RG16,
                        });
                }
                return;
            }
            bool food = assetPath.StartsWith("Assets/Resources/Food/") || assetPath.StartsWith("Assets/Resources/Food3D/");
            bool ui = assetPath.StartsWith("Assets/Resources/UI/");
            if (!food && !ui) return;
            var ti = (TextureImporter)assetImporter;
            ti.textureType = TextureImporterType.Sprite;
            ti.spriteImportMode = SpriteImportMode.Single;
            ti.alphaIsTransparency = true;
            ti.mipmapEnabled = false;
            ti.maxTextureSize = ui ? 2048 : 512;
            ti.textureCompression = TextureImporterCompression.CompressedHQ;
        }
    }
}
