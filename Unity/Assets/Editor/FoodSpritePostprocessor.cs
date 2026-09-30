using UnityEditor;

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
