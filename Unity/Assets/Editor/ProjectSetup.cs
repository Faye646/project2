using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace BianHe.EditorTools
{
    /// <summary>
    /// One-click setup of the 初始 · 1桌 demo, so the scene can be rebuilt whenever the white model
    /// changes (run build_level1.py, copy SM_Level1.fbx into Assets/Art/Models, then BianHe ▸ Setup).
    ///   - URP asset tuned for phones (one shadow cascade, 4x MSAA, no HDR)
    ///   - one toon material per palette entry in Assets/Art/palette.json, remapped onto the FBX
    ///   - Assets/Scenes/Level1.unity: light, camera rig, game flow, the white model
    ///   - landscape player settings; Android (IL2CPP, ARM64) and Windows builds
    /// Batch mode:  Unity -batchmode -quit -projectPath . -executeMethod BianHe.EditorTools.ProjectSetup.SetupAll
    /// </summary>
    public static class ProjectSetup
    {
        const string ModelPath = "Assets/Art/Models/SM_Level1.fbx";
        const string CookSetPath = "Assets/Art/Models/CookSet.fbx";
        const string CookSetJson = "Assets/Resources/cook_set.json";
        static readonly Vector3 CookSetOffset = new Vector3(0, 0, 300);   // far from the shop, never in its view
        const string PalettePath = "Assets/Art/palette.json";
        const string MaterialDir = "Assets/Art/Materials";
        const string ScenePath = "Assets/Scenes/Level1.unity";
        const string SettingsDir = "Assets/Settings";

        // The Blender scene is Z-up with the kitchen's front-left corner at the origin. These are the
        // Blender (x, y) pivots of three props, used to find how Blender's ground plane lands in Unity
        // (update them if build_level1.py moves these props).
        static readonly (string name, Vector2 blender)[] Anchors =
        {
            ("K_Plinth", new Vector2(2.5f, 2.1f)), ("K_ZaoTai", new Vector2(0.55f, 2.3f)), ("K_Walls", new Vector2(0f, 4.2f)),
        };
        static readonly Vector2 BlenderViewDir = new Vector2(-1, 1).normalized;       // camera looks toward -x, +y
        static readonly Vector3 BlenderToLight = new Vector3(-0.3f, -0.8f, 0.52f);     // same light as the Blender toon preview

        [MenuItem("BianHe/Setup Level1 (materials + scene)")]
        public static void SetupAll()
        {
            SetupRenderPipeline();
            SetupMaterials();
            BakeDishIcons();
            SetupScene();
            SetupPlayer();
            AssetDatabase.SaveAssets();
            Debug.Log("[BianHe] setup done");
        }

        // ------------------------------------------------------------------ URP

        static void SetupRenderPipeline()
        {
            Directory.CreateDirectory(SettingsDir);
            var assetPath = SettingsDir + "/Mobile_URP.asset";
            var asset = AssetDatabase.LoadAssetAtPath<UniversalRenderPipelineAsset>(assetPath);
            if (asset == null)
            {
                var create = typeof(UniversalRenderPipelineAsset).GetMethod("CreateRendererAsset", BindingFlags.NonPublic | BindingFlags.Static);
                var renderer = (ScriptableRendererData)create.Invoke(null, new object[] { SettingsDir + "/Mobile_URP.asset", RendererType.UniversalRenderer, true, "Renderer" });
                asset = UniversalRenderPipelineAsset.Create(renderer);
                AssetDatabase.CreateAsset(asset, assetPath);
            }
            var so = new SerializedObject(asset);
            void Set(string prop, Action<SerializedProperty> f)
            {
                var p = so.FindProperty(prop);
                if (p != null) f(p); else Debug.LogWarning("[BianHe] URP field missing: " + prop);
            }
            Set("m_SupportsHDR", p => p.boolValue = false);
            Set("m_MSAA", p => p.intValue = 4);
            Set("m_MainLightShadowsSupported", p => p.boolValue = true);
            Set("m_MainLightShadowmapResolution", p => p.intValue = 2048);
            Set("m_ShadowDistance", p => p.floatValue = 45f);
            Set("m_ShadowCascadeCount", p => p.intValue = 1);
            Set("m_SoftShadowsSupported", p => p.boolValue = true);
            so.ApplyModifiedPropertiesWithoutUndo();
            var rendererList = so.FindProperty("m_RendererDataList");
            if (rendererList != null && rendererList.arraySize > 0)
                EnableSsao(rendererList.GetArrayElementAtIndex(0).objectReferenceValue as ScriptableRendererData);

            GraphicsSettings.defaultRenderPipeline = asset;
            var levels = QualitySettings.names.Length;
            for (int i = 0; i < levels; i++)
            {
                QualitySettings.SetQualityLevel(i, false);
                QualitySettings.renderPipeline = asset;
            }
            EditorUtility.SetDirty(asset);
        }

        // ------------------------------------------------------------------ materials

        static readonly string[] PalettePaths = { PalettePath, "Assets/Art/palette_food.json" };
        const string DishDir = "Assets/Resources/FoodModels";
        const string DishIconDir = "Assets/Resources/Food3D";

        static IEnumerable<string> ModelPaths() =>
            new[] { ModelPath, CookSetPath }.Concat(Directory.GetFiles(DishDir, "*.fbx").Select(f => f.Replace('\\', '/')));

        static void SetupMaterials()
        {
            Directory.CreateDirectory(MaterialDir);
            var shader = Shader.Find("BianHe/ToonLit");
            if (shader == null) throw new Exception("BianHe/ToonLit shader not found");
            var mats = new Dictionary<string, Material>();
            foreach (var palettePath in PalettePaths.Where(File.Exists))
            foreach (JProperty p in JObject.Parse(File.ReadAllText(palettePath))["toon"])
            {
                var path = $"{MaterialDir}/M_{p.Name}.mat";
                var mat = AssetDatabase.LoadAssetAtPath<Material>(path);
                if (mat == null)
                {
                    mat = new Material(shader);
                    AssetDatabase.CreateAsset(mat, path);
                }
                mat.shader = shader;
                ColorUtility.TryParseHtmlString((string)p.Value["lit"], out var lit);
                ColorUtility.TryParseHtmlString((string)p.Value["shade"], out var shade);
                mat.SetColor("_BaseColor", lit);
                mat.SetColor("_ShadeColor", shade);
                mat.SetFloat("_Emission", (float)p.Value["emission"]);
                mat.SetColor("_OutlineColor", OutlineFor(shade));
                mat.SetFloat("_ShadowStrength", 0.6f);
                // thin parts (lattice bars, planks) get thinner lines than the big masses
                mat.SetFloat("_OutlineWidth", p.Name is "Leaf" or "Flower" or "Veg" or "Chili" or "Scallion" ? 1.8f : 2.2f);
                mat.enableInstancing = true;
                ApplyWatercolor(mat, p.Name);
                EditorUtility.SetDirty(mat);
                mats[p.Name] = mat;
            }
            if (File.Exists(CookSetJson))
            {
                var cook = JObject.Parse(File.ReadAllText(CookSetJson));
                foreach (JProperty p in cook["materials"])
                {
                    var path = $"{MaterialDir}/M_{p.Name}.mat";
                    var mat = AssetDatabase.LoadAssetAtPath<Material>(path);
                    if (mat == null) { mat = new Material(shader); AssetDatabase.CreateAsset(mat, path); }
                    ApplyWatercolor(mat, p.Name, (JObject)p.Value);
                    EditorUtility.SetDirty(mat);
                    mats[p.Name] = mat;
                }
                var card = Shader.Find("BianHe/PaintedCard");
                foreach (JProperty p in cook["cards"])
                {
                    var path = $"{MaterialDir}/M_{p.Name}.mat";
                    var mat = AssetDatabase.LoadAssetAtPath<Material>(path);
                    if (mat == null) { mat = new Material(card); AssetDatabase.CreateAsset(mat, path); }
                    mat.shader = card;
                    mat.SetTexture("_MainTex", AssetDatabase.LoadAssetAtPath<Texture2D>($"{TextureDir}/{(string)p.Value}.png"));
                    mat.SetFloat("_Flicker", p.Name == "Card_FireMouth" ? 1 : 0);
                    EditorUtility.SetDirty(mat);
                    mats[p.Name] = mat;
                }
            }
            foreach (var modelPath in ModelPaths())
            {
                var importer = (ModelImporter)AssetImporter.GetAtPath(modelPath);
                foreach (var kv in mats)
                    importer.AddRemap(new AssetImporter.SourceAssetIdentifier(typeof(Material), "M_" + kv.Key), kv.Value);
                importer.materialImportMode = ModelImporterMaterialImportMode.ImportStandard;
                importer.SaveAndReimport();
            }
        }

        // ------------------------------------------------------------------ 三渲二 dish images

        /// <summary>
        /// Renders each food model (Resources/FoodModels/SM_&lt;id&gt;.fbx: dishes, ingredients, seasonings)
        /// with the toon shader into a transparent 512² image, Resources/Food3D/&lt;id&gt;.png, seen from the
        /// front and a little left, about 32° from above, like the art. The UI shows these instead of flat pictures.
        /// </summary>
        [MenuItem("BianHe/Bake 3D Food Images")]
        public static void BakeDishIcons()
        {
            Directory.CreateDirectory(DishIconDir);
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            var lightGo = new GameObject("Sun");
            var light = lightGo.AddComponent<Light>();
            light.type = LightType.Directional;
            light.intensity = 1.2f;
            light.shadows = LightShadows.None;
            lightGo.transform.rotation = Quaternion.LookRotation(-new Vector3(-0.3f, 0.52f, -0.8f).normalized);
            var camGo = new GameObject("IconCam");
            var cam = camGo.AddComponent<Camera>();
            camGo.AddComponent<UniversalAdditionalCameraData>();
            cam.orthographic = true;
            cam.orthographicSize = 0.12f;
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = new Color(0, 0, 0, 0);
            cam.nearClipPlane = 0.01f;
            cam.farClipPlane = 10f;
            const int size = 512;
            var rt = new RenderTexture(size, size, 24, RenderTextureFormat.ARGB32) { antiAliasing = 8 };
            cam.targetTexture = rt;
            Shader.SetGlobalFloat("_ToonOutlineScale", 1.9f);   // lines as thick as in the art at icon size
            foreach (var path in Directory.GetFiles(DishDir, "SM_*.fbx"))
            {
                var model = AssetDatabase.LoadAssetAtPath<GameObject>(path.Replace('\\', '/'));
                var go = (GameObject)PrefabUtility.InstantiatePrefab(model);
                var b = new Bounds(go.transform.position, Vector3.zero);
                foreach (var r in go.GetComponentsInChildren<Renderer>()) b.Encapsulate(r.bounds);
                // Blender view (az 20°, el 32°): Unity (x, height, z) = Blender (x, y, z)
                float az = 20f * Mathf.Deg2Rad, el = 32f * Mathf.Deg2Rad;
                var view = new Vector3(Mathf.Sin(az) * Mathf.Cos(el), Mathf.Sin(el), -Mathf.Cos(az) * Mathf.Cos(el));
                var target = b.center;
                camGo.transform.position = target + view * 2f;
                camGo.transform.LookAt(target);
                cam.orthographicSize = Mathf.Max(b.size.x, b.size.y, b.size.z) * 0.6f;
                cam.Render();
                var prev = RenderTexture.active;
                RenderTexture.active = rt;
                var tex = new Texture2D(size, size, TextureFormat.RGBA32, false);
                tex.ReadPixels(new Rect(0, 0, size, size), 0, 0);
                tex.Apply();
                RenderTexture.active = prev;
                var id = Path.GetFileNameWithoutExtension(path).Substring(3);   // SM_D01 → D01
                File.WriteAllBytes($"{DishIconDir}/{id}.png", tex.EncodeToPNG());
                UnityEngine.Object.DestroyImmediate(tex);
                UnityEngine.Object.DestroyImmediate(go);
                Debug.Log($"[BianHe] baked {DishIconDir}/{id}.png");
            }
            cam.targetTexture = null;
            rt.Release();
            AssetDatabase.Refresh();
        }

        // ------------------------------------------------------------------ 水彩 (style C)

        const string WcTablePath = "Assets/Art/wc_materials.json";
        const string TextureDir = "Assets/Art/Textures";
        static JObject wcTable, cookTable;

        /// <summary>
        /// Materials listed in wc_materials.json (written by build_level1.py --wc) switch to
        /// BianHe/WatercolorLit: painted patch, saturation/value, dappled light, flat colours.
        /// </summary>
        static void ApplyWatercolor(Material mat, string name, JObject entry = null)
        {
            if (wcTable == null && File.Exists(WcTablePath)) wcTable = JObject.Parse(File.ReadAllText(WcTablePath));
            if (cookTable == null && File.Exists(CookSetJson)) cookTable = (JObject)JObject.Parse(File.ReadAllText(CookSetJson))["materials"];
            var e = entry ?? wcTable?[name] ?? cookTable?["C_" + name];
            var shader = Shader.Find("BianHe/WatercolorLit");
            if (e == null || shader == null) return;
            mat.shader = shader;
            ColorUtility.TryParseHtmlString((string)e["lit"], out var lit);
            ColorUtility.TryParseHtmlString((string)e["shade"], out var shade);
            mat.SetColor("_BaseColor", lit);
            mat.SetColor("_ShadeColor", shade);
            var tex = (string)e["tex"];
            var t2d = tex == null ? null : AssetDatabase.LoadAssetAtPath<Texture2D>($"{TextureDir}/{tex}.png");
            mat.SetTexture("_PaintTex", t2d);
            mat.SetFloat("_UsePaint", t2d != null ? 1 : 0);
            mat.SetFloat("_PaintScale", (float)e["scale"]);
            mat.SetFloat("_Saturation", (float)e["sat"]);
            mat.SetFloat("_Value", (float)e["val"]);
            mat.SetFloat("_Dappled", (bool)e["dappled"] ? 1 : 0);
            mat.SetFloat("_Emission", (bool)e["emissive"] ? 1 : 0);
            mat.SetTexture("_NoiseTex", AssetDatabase.LoadAssetAtPath<Texture2D>($"{TextureDir}/wc_noise.png"));
            mat.SetColor("_OutlineColor", new Color(0.42f, 0.27f, 0.19f));
            mat.SetFloat("_OutlineWidth", 1.6f);
        }

        /// <summary>Adds URP's SSAO to the renderer (pigment pooling in corners), if this URP exposes it.</summary>
        static void EnableSsao(ScriptableRendererData renderer)
        {
            if (renderer == null || renderer.rendererFeatures.Exists(f => f != null && f.GetType().Name == "ScreenSpaceAmbientOcclusion")) return;
            var type = typeof(UniversalRenderPipelineAsset).Assembly.GetType("UnityEngine.Rendering.Universal.ScreenSpaceAmbientOcclusion");
            if (type == null) { Debug.LogWarning("[BianHe] SSAO feature not found"); return; }
            var feature = (ScriptableRendererFeature)ScriptableObject.CreateInstance(type);
            feature.name = "SSAO";
            AssetDatabase.AddObjectToAsset(feature, renderer);
            renderer.rendererFeatures.Add(feature);
            var so = new SerializedObject(renderer);
            var map = so.FindProperty("m_RendererFeatureMap");
            if (map != null)
            {
                map.arraySize++;
                AssetDatabase.TryGetGUIDAndLocalFileIdentifier(feature, out _, out long id);
                map.GetArrayElementAtIndex(map.arraySize - 1).longValue = id;
                so.ApplyModifiedPropertiesWithoutUndo();
            var rendererList = so.FindProperty("m_RendererDataList");
            if (rendererList != null && rendererList.arraySize > 0)
                EnableSsao(rendererList.GetArrayElementAtIndex(0).objectReferenceValue as ScriptableRendererData);
            }
            EditorUtility.SetDirty(renderer);
        }

        /// <summary>Ink colour for a material: its shade colour pushed dark and warm, like the art's brown lines.</summary>
        static Color OutlineFor(Color shade)
        {
            Color.RGBToHSV(shade, out float h, out float s, out float v);
            var ink = Color.HSVToRGB(h, Mathf.Clamp01(s * 0.8f + 0.2f), v * 0.32f);
            return Color.Lerp(ink, new Color(0.24f, 0.15f, 0.09f), 0.5f);
        }

        // ------------------------------------------------------------------ scene

        static void SetupScene()
        {
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            var model = AssetDatabase.LoadAssetAtPath<GameObject>(ModelPath);
            var level = (GameObject)PrefabUtility.InstantiatePrefab(model);
            level.name = "Level1";

            // how Blender's ground axes land in Unity (FBX axis conversion), from three known pivots
            var map = SolveGroundMap(level.transform);
            Vector2 viewU = map.MultiplyVector(BlenderViewDir);
            float yaw = Mathf.Atan2(viewU.x, viewU.y) * Mathf.Rad2Deg;
            Vector2 lightH = map.MultiplyVector(new Vector2(BlenderToLight.x, BlenderToLight.y));
            var toLight = new Vector3(lightH.x, BlenderToLight.z, lightH.y).normalized;

            var lightGo = new GameObject("Sun");
            var light = lightGo.AddComponent<Light>();
            light.type = LightType.Directional;
            light.color = new Color(1f, 0.97f, 0.9f);
            light.intensity = 1.2f;
            light.shadows = LightShadows.Soft;
            light.shadowStrength = 1f;
            light.shadowBias = 0.05f;
            light.shadowNormalBias = 0.3f;
            lightGo.transform.rotation = Quaternion.LookRotation(-toLight);

            RenderSettings.ambientMode = AmbientMode.Flat;
            RenderSettings.ambientLight = new Color(0.8f, 0.78f, 0.72f);
            RenderSettings.skybox = null;

            var camGo = new GameObject("Main Camera") { tag = "MainCamera" };
            var cam = camGo.AddComponent<Camera>();
            cam.orthographic = true;
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = UIKit.Hex("#f4ecd9");   // paper, as behind the level art
            cam.nearClipPlane = 1f;
            cam.farClipPlane = 160f;
            camGo.AddComponent<UniversalAdditionalCameraData>();
            var rig = camGo.AddComponent<CameraRig>();
            rig.yaw = yaw;
            rig.pitch = 30f;
            rig.distance = 70f;
            rig.groundHeight = 0.45f;

            var cookModel = AssetDatabase.LoadAssetAtPath<GameObject>(CookSetPath);
            Transform cookSet = null;
            if (cookModel != null)
            {
                var cs = (GameObject)PrefabUtility.InstantiatePrefab(cookModel);
                cs.name = "CookSet";
                cs.transform.position = CookSetOffset;
                cookSet = cs.transform;
            }

            var flowGo = new GameObject("GameFlow");
            var flow = flowGo.AddComponent<GameFlow>();
            flow.rig = rig;
            flow.level = level.transform;
            flow.cookSet = cookSet;

            Directory.CreateDirectory(Path.GetDirectoryName(ScenePath));
            EditorSceneManager.SaveScene(scene, ScenePath);
            EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(ScenePath, true) };
            Debug.Log($"[BianHe] scene saved, camera yaw {yaw:0.0}°, light {toLight}");
        }

        /// <summary>2x2 matrix (in a Matrix4x4) taking Blender ground (x, y) directions to Unity (x, z).</summary>
        static Matrix4x4 SolveGroundMap(Transform level)
        {
            Vector2 U(string n)
            {
                var t = level.GetComponentsInChildren<Transform>(true).First(c => c.name == n);
                return new Vector2(t.position.x, t.position.z);
            }
            Vector2 u0 = U(Anchors[0].name), u1 = U(Anchors[1].name), u2 = U(Anchors[2].name);
            Debug.Log($"[BianHe] anchors in Unity: {u0} {u1} {u2}");
            Vector2 b0 = Anchors[0].blender, b1 = Anchors[1].blender, b2 = Anchors[2].blender;
            // [du1 du2] = A [db1 db2]  →  A = [du1 du2] [db1 db2]^-1
            Vector2 db1 = b1 - b0, db2 = b2 - b0, du1 = u1 - u0, du2 = u2 - u0;
            float det = db1.x * db2.y - db2.x * db1.y;
            var inv = new Vector4(db2.y / det, -db1.y / det, -db2.x / det, db1.x / det); // (a b; c d) of the inverse
            var m = Matrix4x4.identity;
            m.m00 = du1.x * inv.x + du2.x * inv.y;
            m.m01 = du1.x * inv.z + du2.x * inv.w;
            m.m10 = du1.y * inv.x + du2.y * inv.y;
            m.m11 = du1.y * inv.z + du2.y * inv.w;
            return m;
        }

        // ------------------------------------------------------------------ player & builds

        static void SetupPlayer()
        {
            PlayerSettings.companyName = "BianHe";
            PlayerSettings.productName = "汴河两岸";
            PlayerSettings.defaultInterfaceOrientation = UIOrientation.AutoRotation;
            PlayerSettings.allowedAutorotateToPortrait = false;
            PlayerSettings.allowedAutorotateToPortraitUpsideDown = false;
            PlayerSettings.allowedAutorotateToLandscapeLeft = true;
            PlayerSettings.allowedAutorotateToLandscapeRight = true;
            PlayerSettings.colorSpace = ColorSpace.Linear;
            PlayerSettings.SetApplicationIdentifier(UnityEditor.Build.NamedBuildTarget.Android, "com.bianhe.level1demo");
            PlayerSettings.SetScriptingBackend(UnityEditor.Build.NamedBuildTarget.Android, ScriptingImplementation.IL2CPP);
            PlayerSettings.Android.targetArchitectures = AndroidArchitecture.ARM64;
            PlayerSettings.Android.minSdkVersion = AndroidSdkVersions.AndroidApiLevel26;
            PlayerSettings.bundleVersion = "0.1.0";

            // iOS: needs a Mac with Xcode to compile and sign; these settings travel with the project
            PlayerSettings.SetApplicationIdentifier(UnityEditor.Build.NamedBuildTarget.iOS, "com.bianhe.level1demo");
            PlayerSettings.iOS.targetOSVersionString = "15.0";
            PlayerSettings.iOS.buildNumber = "1";
            PlayerSettings.iOS.appleEnableAutomaticSigning = true;
            PlayerSettings.iOS.requiresFullScreen = true;

            // WebGL (plays in iPhone Safari): Brotli with a JS fallback so any static server works
            PlayerSettings.WebGL.compressionFormat = WebGLCompressionFormat.Brotli;
            PlayerSettings.WebGL.decompressionFallback = true;
            PlayerSettings.WebGL.dataCaching = true;
            PlayerSettings.fullScreenMode = FullScreenMode.Windowed;
            PlayerSettings.defaultScreenWidth = 1920;
            PlayerSettings.defaultScreenHeight = 1080;
            PlayerSettings.resizableWindow = true;
        }

        [MenuItem("BianHe/Build Android APK")]
        public static void BuildAndroid() => Build(BuildTarget.Android, "../Builds/BianHe_Level1.apk");

        [MenuItem("BianHe/Build WebGL")]
        public static void BuildWebGL() => Build(BuildTarget.WebGL, "../Builds/WebGL");

        [MenuItem("BianHe/Build Windows")]
        public static void BuildWindows() => Build(BuildTarget.StandaloneWindows64, "../Builds/Windows/BianHe.exe");

        static void Build(BuildTarget target, string path)
        {
            var report = BuildPipeline.BuildPlayer(new BuildPlayerOptions
            {
                scenes = new[] { ScenePath },
                locationPathName = path,
                target = target,
                options = BuildOptions.None,
            });
            Debug.Log($"[BianHe] build {target}: {report.summary.result}, {report.summary.totalSize / 1048576f:0.0} MB, {report.summary.totalTime}");
            if (report.summary.result != BuildResult.Succeeded && Application.isBatchMode) EditorApplication.Exit(1);
        }
    }
}
