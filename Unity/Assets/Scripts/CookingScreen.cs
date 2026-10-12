using System;
using System.Collections.Generic;
using System.Linq;
using BianHe.Core;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEngine.UI;

namespace BianHe
{
    /// <summary>
    /// 做饭界面, laid out after the 烹饪 mock-up (eg.jpg): a first-person view of the kitchen counter in
    /// three parts — 放置区 (trays for finished dishes), 食材与调味 (the board), 灶台 (four blocks side by side,
    /// a wok and a fire mouth each, and the 火候 gauge) — with the chosen dish top left and 出锅 bottom right.
    ///
    /// Play: pick a dish → tap what it needs on the board (it lights up; the raw ingredients drop into a wok)
    /// → the wok starts once everything is in, the raw ingredients tossed about in it → tap 出锅 while the
    /// needle is in the gold band: they turn into the finished dish in the wok → 装盘 (the same button, or by
    /// itself with 自动装盘 on) flies it onto a free tray → tap the tray to carry the dish to its table.
    /// The stove's blocks open by 声望 (one at 一级①, one more with each upgrade; a closed one has its lid on and
    /// its fire out). Each wok cooks on its own: a tap on a wok picks it, and the gauge, 出锅 and 装盘 are for the
    /// picked one (a tap on the picked wok does the same as the button, and on any wok whose needle is in the gold or
    /// whose dish is out, at once); what goes in from the board goes into the picked wok, or the next free one if that
    /// is busy. A card over each wok says how it is doing, with a small
    /// 火候 bar while it cooks. The gauge shows CookRules: the needle swings over a gold band; within the time limit
    /// (cook time + 3 s) gold is 完美 and anywhere else 没熟, and after the limit it's 糊了. Stoves keep cooking
    /// while the screen is closed. The room, counter, trays, stove and woks are a 3D set (CookSet.fbx, built by
    /// build_cook_view.py --export in the approved 水彩 style) seen through its own camera; the food on it is 3D
    /// too. The UI is pinned over the set's markers (Resources/cook_set.json) every frame.
    /// </summary>
    public class CookingScreen : MonoBehaviour
    {
        public event Action Closed;
        public bool IsOpen { get; private set; }

        GameSession session;
        Canvas canvas;
        CanvasGroup group;
        Recipe selected;
        int stoveIndex;                          // the picked block of the stove
        readonly List<Burner> burners = new();   // the stove's blocks, left to right

        // views
        Image headerDish;
        Text headerName;
        RectTransform picker;
        readonly List<(Recipe r, Text pending, Text auto)> pickerCards = new();
        readonly List<(string id, Image img, Image ring, Text check, CanvasGroup cg)> items = new();
        readonly List<(Image dish, Text label, Image badge, Text badgeText)> trays = new();
        readonly List<(RectTransform card, Image img, Text text)> orderViews = new();
        Text orderNote, gaugeHint, resultText, cookButtonText;
        Image needle, cookButton;
        readonly Image[] gaugeZones = new Image[5];
        Image timeBar;
        Text toast;
        Image toastBg;
        float toastUntil, resultUntil, fade;
        int trayArmed = -1;
        float trayArmedUntil;

        static readonly Color Gold = UIKit.Hex("#f2b53a");
        static readonly Color Raw = UIKit.Hex("#dfe8c8");
        static readonly Color Burn = UIKit.Hex("#c0462c");
        static readonly Color Green = UIKit.Hex("#6f9a45");
        static readonly Color Immortal = UIKit.Hex("#ffe27a");
        static readonly Color PlaqueWood = UIKit.Hex("#e9c993");

        // the 3D set
        Transform setRoot;
        Camera setCam;
        JObjectLite markers;
        RectTransform pinLayer;
        readonly List<(RectTransform rt, Vector3 world, Vector2 half)> pins = new();
        readonly Dictionary<string, (Vector3 pos, float scale, float rot)> boardSpots = new();
        readonly List<(Vector3 pos, float scale)> traySpots = new();
        Vector3 camHome;   // where the cook camera stands (the video's close-ups move it and bring it back)
        readonly GameObject[] trayModels = new GameObject[GameSession.TrayCount];
        readonly string[] trayModelIds = new string[GameSession.TrayCount];
        readonly float[] trayLandAt = new float[GameSession.TrayCount];
        GameObject flying;
        Vector3 flyFrom, flyTo, flyScale0, flyScale1;
        float flyStart;
        Text autoPlateText;
        Image autoPlateBg;
        const float FlySeconds = 0.55f;

        static readonly string[] SeasoningOrder = { "salt", "oil", "scallion", "ginger" };   // 糖 joins when a dish needs it

        /// <summary>
        /// One block of the stove: its wok, fire mouth and lid in the set (Wok&lt;k&gt;, FireMouth&lt;k&gt;, Lid&lt;k&gt;), what is
        /// in its wok (the raw ingredients, Resources/FoodModels/RAW_&lt;id&gt; built by build_raw.py, dropped in and tossed
        /// about while the dish cooks, then the finished dish SM_&lt;dish&gt;_wok from 出锅 until 装盘 flies it to a tray),
        /// the dish being put together in it, the glow of its fire, the steam over it and the card above it.
        /// </summary>
        class Burner
        {
            public int Index;
            public Vector3 Spot;                 // over the wok (cook_set.json woks[k])
            public float Scale = 1f;             // the finished dish's scale there
            public Vector3 Fire;                 // its fire mouth
            public Vector3 Axis;                 // the middle of its wok's inside, at the bottom
            public float K = 1f;                 // its wok over the one WokProfile describes
            public Renderer[] Wok = new Renderer[0], Lid = new Renderer[0];
            public Renderer FireCard;
            public readonly List<RawPiece> Raw = new();
            public string RawKey = "";
            public GameObject Done;
            public string DoneId;
            public float DoneSince;
            public Vector3 DoneScale;
            public Recipe PrepDish;              // the dish being put together in it …
            public readonly HashSet<string> Prep = new();   // … and what of it is in already
            public Image Glow, CardBg, Gold, Tick;
            public Outline CardEdge;
            public RectTransform Bar;
            public Text CardText;
            public readonly List<Image> Steam = new();
            public string Result;                // 完美！ and the like, for a moment after 出锅
            public Color ResultColor;
            public float ResultUntil;
        }

        readonly MaterialPropertyBlock mpb = new();
        static readonly int TintId = Shader.PropertyToID("_Tint");
        static readonly int FlickerId = Shader.PropertyToID("_Flicker");
        static readonly int HighlightId = Shader.PropertyToID("_Highlight");

        public void Build(GameSession s, Transform cookSet)
        {
            session = s;
            setRoot = cookSet;
            LoadSet();
            canvas = UIKit.Canvas("CookingScreen", 10);
            canvas.transform.SetParent(transform, false);
            group = canvas.gameObject.AddComponent<CanvasGroup>();
            var root = canvas.transform;

            // the 3D set shows through; UI for things on it is pinned to their markers
            pinLayer = UIKit.Rect(root, "Pins", Vector2.zero, Vector2.one);
            var art = UIKit.Rect(root, "Art", Vector2.zero, Vector2.one);
            var fit = art.gameObject.AddComponent<AspectRatioFitter>();
            fit.aspectMode = AspectRatioFitter.AspectMode.EnvelopeParent;
            fit.aspectRatio = 16f / 9f;
            BuildTrays(pinLayer);
            BuildBoard(pinLayer);
            BuildStove(art, root);
            BuildTop(root);
            BuildPicker(root);

            var toastRt = UIKit.Rect(root, "Toast", new Vector2(0.3f, 0.62f), new Vector2(0.7f, 0.62f), new Vector2(0, -50), new Vector2(0, 50));
            toastBg = UIKit.Panel(toastRt, UIKit.Ink, false);
            toastBg.raycastTarget = false;
            toast = UIKit.Label(toastRt, "", 36, Color.white);
            toastRt.gameObject.SetActive(false);

            session.Plated += OnPlated;
            canvas.gameObject.SetActive(false);
        }

        // ------------------------------------------------------------------ the 3D set

        void LoadSet()
        {
            markers = new JObjectLite(Resources.Load<TextAsset>("cook_set").text);
            var o = setRoot.position;
            foreach (var m in markers.List("board"))
                boardSpots[m.Str("id")] = (o + m.Vec("pos"), m.Num("scale"), m.Num("rot"));
            foreach (var m in markers.List("trays"))
                traySpots.Add((o + m.Vec("pos"), m.Num("scale")));
            // the stove's blocks, left to right: over each wok, and its fire mouth (an older set has one of each)
            var woks = markers.Has("woks") ? markers.List("woks").ToList() : new List<JObjectLite> { markers.Obj("wok") };
            for (int k = 0; k < Mathf.Min(woks.Count, session.Stoves.Count); k++)
                burners.Add(new Burner { Index = k, Spot = o + woks[k].Vec("pos"), Scale = woks[k].Num("scale") });
            markers.Offset = o;
            var fires = markers.Has("fires") ? markers.Vecs("fires").ToList() : new List<Vector3> { markers.Vec("fire") };
            foreach (var b in burners) b.Fire = fires[Mathf.Min(b.Index, fires.Count - 1)];

            var cam = markers.Obj("camera");
            var go = new GameObject("CookCamera");
            go.transform.SetParent(transform, false);
            setCam = go.AddComponent<Camera>();
            go.AddComponent<UnityEngine.Rendering.Universal.UniversalAdditionalCameraData>();
            go.transform.SetPositionAndRotation(o + cam.Vec("pos"), Quaternion.LookRotation(cam.Vec("forward"), cam.Vec("up")));
            camHome = go.transform.position;
            MeasureSet();
            setCam.usePhysicalProperties = true;
            setCam.focalLength = cam.Num("focal");
            setCam.sensorSize = new Vector2(cam.Num("sensor"), cam.Num("sensor") * 9f / 16f);
            setCam.gateFit = Camera.GateFitMode.Overscan;   // never crop the set on narrow or wide screens
            setCam.clearFlags = CameraClearFlags.SolidColor;
            setCam.backgroundColor = UIKit.Hex("#3b2a1c");
            setCam.nearClipPlane = 0.05f;
            setCam.farClipPlane = 9f;   // the set is within a few metres: the shadow map spans only that, sharp
            setCam.depth = 5;
            setCam.enabled = false;
        }

        void Pin(RectTransform rt, Vector3 world, Vector2 halfMetres)
        {
            rt.anchorMin = rt.anchorMax = new Vector2(0.5f, 0.5f);
            pins.Add((rt, world, halfMetres));
        }

        /// <summary>Keeps every pinned rect over its 3D spot, sized to what that spot covers on screen.</summary>
        void UpdatePins()
        {
            foreach (var (rt, world, half) in pins)
            {
                var parent = (RectTransform)rt.parent;
                Vector2 Local(Vector3 w)
                {
                    RectTransformUtility.ScreenPointToLocalPointInRectangle(parent, setCam.WorldToScreenPoint(w), null, out var lp);
                    return lp;
                }
                var c = Local(world);
                var r = Local(world + setCam.transform.right * half.x);
                var u = Local(world + setCam.transform.up * half.y);
                rt.anchoredPosition = c;
                rt.sizeDelta = new Vector2(Mathf.Abs(r.x - c.x) * 2, Mathf.Abs(u.y - c.y) * 2);
            }
        }

        GameObject SpawnFood(string id, Vector3 pos, float scale, float rotRad)
        {
            var prefab = Resources.Load<GameObject>("FoodModels/SM_" + id);
            if (prefab == null) return null;
            var go = Instantiate(prefab, pos, Quaternion.Euler(0, -rotRad * Mathf.Rad2Deg, 0) * prefab.transform.rotation, setRoot);
            go.transform.localScale = prefab.transform.localScale * scale;
            go.name = "Food_" + id;
            return go;
        }

        // ------------------------------------------------------------------ layout

        static RectTransform Plaque(Transform parent, string text, float x0, float x1, float y0 = 0.205f, float y1 = 0.25f)
        {
            var rt = UIKit.Rect(parent, "Plaque_" + text, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f));
            UIKit.Panel(rt, PlaqueWood).raycastTarget = false;
            UIKit.Label(rt, text, 28, UIKit.Ink, TextAnchor.MiddleCenter, FontStyle.Bold);
            return rt;
        }

        void BuildTrays(RectTransform art)
        {
            var mid = (traySpots[0].pos + traySpots[traySpots.Count - 1].pos) / 2;
            Pin(Plaque(art, "放置区", 0, 0), mid + new Vector3(0, -0.2f, -0.42f), new Vector2(0.4f, 0.045f));
            for (int i = 0; i < GameSession.TrayCount; i++)
            {
                int idx = i;
                var t = UIKit.Rect(art, "Tray" + i, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f));
                Pin(t, traySpots[i].pos + new Vector3(0, 0.02f, 0), new Vector2(0.27f, 0.13f));
                var hit = t.gameObject.AddComponent<Image>();
                hit.color = Color.clear;
                var b = t.gameObject.AddComponent<Button>();
                b.transition = Selectable.Transition.None;
                b.onClick.AddListener(() => TapTray(idx));
                var dish = UIKit.Img(t, "Dish", null, Color.white, new Vector2(0.02f, 0.05f), new Vector2(0.98f, 1.35f), preserveAspect: true);
                var lab = UIKit.Rect(t, "Label", new Vector2(-0.05f, -0.34f), new Vector2(1.05f, -0.04f));
                var labBg = UIKit.Panel(lab, new Color(UIKit.Ink.r, UIKit.Ink.g, UIKit.Ink.b, 0.75f), false);
                labBg.raycastTarget = false;
                var label = UIKit.Label(lab, "", 20, Color.white);
                var badgeRt = UIKit.Rect(t, "Badge", new Vector2(0.5f, 1.05f), new Vector2(1.05f, 1.35f));
                var badge = UIKit.Panel(badgeRt, Green, false);
                badge.raycastTarget = false;
                var bt = UIKit.Label(badgeRt, "", 20, Color.white, TextAnchor.MiddleCenter, FontStyle.Bold);
                trays.Add((dish, label, badge, bt));
            }
        }

        void BuildBoard(RectTransform art)
        {
            var c = boardSpots.Values.Aggregate(Vector3.zero, (a, b) => a + b.pos) / Mathf.Max(1, boardSpots.Count);
            Pin(Plaque(art, "食材与调味", 0, 0), c + new Vector3(0, -0.2f, -0.52f), new Vector2(0.45f, 0.045f));
            // one spot on the board per ingredient/seasoning (cook_set.json); the 3D food sits there
            var ids = session.OpenRecipes().SelectMany(r => r.Ingredients.Keys).Distinct().Concat(SeasoningOrder).ToList();
            var onBoard = new List<GameObject>();
            foreach (var id in ids)
            {
                if (!boardSpots.TryGetValue(id, out var spot)) continue;
                AddItem(art, id, Vector2.zero, Vector2.zero);
                Pin((RectTransform)items[items.Count - 1].cg.transform, spot.pos + new Vector3(0, 0.1f, 0), new Vector2(0.16f, 0.14f));
                var go = SpawnFood(id, spot.pos, spot.scale, spot.rot);
                if (go) onBoard.Add(go);
            }
            SettleOnBoard(onBoard);
        }

        void AddItem(RectTransform zone, string id, Vector2 a0, Vector2 a1)
        {
            var cell = UIKit.Rect(zone, "Item_" + id, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f));
            var cg = cell.gameObject.AddComponent<CanvasGroup>();
            var hit = cell.gameObject.AddComponent<Image>();
            hit.color = Color.clear;
            var btn = cell.gameObject.AddComponent<Button>();
            btn.transition = Selectable.Transition.None;
            btn.onClick.AddListener(() => TapItem(id));
            var ring = UIKit.Img(cell, "Glow", UIKit.Circle, new Color(1f, 0.86f, 0.45f, 0.3f), new Vector2(0.02f, 0.02f), new Vector2(0.98f, 0.98f), preserveAspect: true);
            var sprite = DishSprite(id);
            Image img;
            if (sprite != null)
                img = UIKit.Img(cell, "Pic", sprite, Color.white, new Vector2(0.04f, 0.1f), new Vector2(0.96f, 1f), preserveAspect: true);
            else
            {   // no art yet: a plain jar with the name on it
                img = UIKit.Img(cell, "Pic", UIKit.Circle, UIKit.Hex("#e9e4d4"), new Vector2(0.2f, 0.15f), new Vector2(0.8f, 0.9f), preserveAspect: true);
                UIKit.Label(img.transform, session.Data.IngredientName(id), 34, UIKit.InkSoft, TextAnchor.MiddleCenter, FontStyle.Bold);
            }
            var nameRt = UIKit.Rect(cell, "Name", new Vector2(0.2f, -0.02f), new Vector2(0.8f, 0.16f));
            UIKit.Panel(nameRt, new Color(1f, 0.97f, 0.9f, 0.85f), false).raycastTarget = false;
            UIKit.Label(nameRt, session.Data.IngredientName(id), 18, UIKit.Ink, TextAnchor.MiddleCenter, FontStyle.Bold);
            var chk = UIKit.Rect(cell, "Check", new Vector2(0.62f, 0.62f), new Vector2(1f, 1f));
            var check = UIKit.Label(chk, "✓", 40, Green, TextAnchor.MiddleCenter, FontStyle.Bold);
            check.gameObject.AddComponent<Outline>().effectColor = Color.white;
            items.Add((id, img, ring, check, cg));
        }

        void BuildStove(RectTransform art, Transform root)
        {
            Pin(Plaque(art, "灶台", 0, 0), markers.Vec("fire") + new Vector3(0, 0.4f, -0.02f), new Vector2(0.2f, 0.045f));
            foreach (var bl in burners) BuildBurner(art, bl);

            // 火候 gauge above the stove: stacked half rings, each filled from the left up to its end, so
            // the gold band (and the 仙味 core for 高等菜) sits in the middle: raw | gold | core | gold | raw
            var gauge = UIKit.Rect(art, "Gauge", new Vector2(0.745f, 0.64f), new Vector2(0.945f, 0.855f));
            // a solid face, so the shelf jars and the chili string behind the dial don't show through the ring
            UIKit.Img(gauge, "Face", UIKit.HalfDisc, new Color(UIKit.Paper.r, UIKit.Paper.g, UIKit.Paper.b, 0.95f), new Vector2(-0.03f, -0.03f), new Vector2(1.03f, 1.06f));
            UIKit.Img(gauge, "Back", UIKit.HalfRing, new Color(0.98f, 0.95f, 0.88f, 0.95f), new Vector2(-0.03f, -0.03f), new Vector2(1.03f, 1.06f));
            Color[] zoneColors = { Raw, Gold, Immortal, Gold, Raw };
            for (int i = 0; i < gaugeZones.Length; i++)
            {
                var z = UIKit.Img(gauge, "Zone" + i, UIKit.HalfRing, zoneColors[i], Vector2.zero, Vector2.one);
                z.type = Image.Type.Filled;
                z.fillMethod = Image.FillMethod.Radial180;
                z.fillOrigin = (int)Image.Origin180.Bottom;
                z.fillClockwise = true;
                gaugeZones[i] = z;
            }
            var pivot = UIKit.Rect(gauge, "NeedlePivot", new Vector2(0.5f, 0f), new Vector2(0.5f, 0f));
            pivot.sizeDelta = Vector2.zero;
            var n = UIKit.Rect(pivot, "Needle", new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f));
            n.pivot = new Vector2(0.5f, 0f);
            n.sizeDelta = new Vector2(8, 190);
            needle = n.gameObject.AddComponent<Image>();
            needle.color = UIKit.Ink;
            needle.raycastTarget = false;
            UIKit.Img(pivot, "Hub", UIKit.Circle, UIKit.Ink, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f)).rectTransform.sizeDelta = new Vector2(28, 28);
            var hint = UIKit.Rect(art, "GaugeHint", new Vector2(0.72f, 0.585f), new Vector2(0.97f, 0.63f));
            UIKit.Panel(hint, new Color(UIKit.Paper.r, UIKit.Paper.g, UIKit.Paper.b, 0.92f), false);
            gaugeHint = UIKit.Label(hint, "", 22, UIKit.Ink);
            var bar = UIKit.Rect(hint, "TimeLeft", new Vector2(0, 0), new Vector2(1, 0), new Vector2(8, 3), new Vector2(-8, 9));
            timeBar = UIKit.Panel(bar, Green, false);
            timeBar.type = Image.Type.Filled;
            timeBar.fillMethod = Image.FillMethod.Horizontal;
            var res = UIKit.Rect(art, "Result", new Vector2(0.765f, 0.665f), new Vector2(0.925f, 0.755f));   // inside the arc
            resultText = UIKit.Label(res, "", 56, UIKit.Hex("#d9861c"), TextAnchor.MiddleCenter, FontStyle.Bold);
            resultText.gameObject.AddComponent<Outline>().effectColor = new Color(1, 1, 1, 0.85f);

            // 出锅 (then 装盘) sticks to the screen corner so a wide phone never crops it; 自动装盘 switch above it
            var btn = UIKit.Rect(root, "CookButton", new Vector2(0.79f, 0.03f), new Vector2(0.975f, 0.135f));
            var b = UIKit.Button(btn, "出锅", 52, Green, Color.white, TapCook);
            cookButton = (Image)b.targetGraphic;
            cookButtonText = btn.GetComponentInChildren<Text>();
            var auto = UIKit.Rect(root, "AutoPlate", new Vector2(0.645f, 0.045f), new Vector2(0.775f, 0.115f));
            var ab = UIKit.Button(auto, "自动装盘", 26, PlaqueWood, UIKit.Ink, () => session.AutoPlate = !session.AutoPlate);
            autoPlateBg = (Image)ab.targetGraphic;
            autoPlateText = auto.GetComponentInChildren<Text>();
        }

        /// <summary>
        /// One block's UI: the glow of its fire, the steam over its wok (the food in it is 3D), a tap area on the wok,
        /// and the card above it (what it is doing; a small 火候 bar while it cooks). A tap on the wok or its card picks
        /// it; on the picked one it does what 出锅 / 装盘 does.
        /// </summary>
        void BuildBurner(RectTransform art, Burner b)
        {
            int k = b.Index;
            b.Glow = UIKit.Img(pinLayer, "FireGlow" + k, UIKit.Circle, UIKit.Fire, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f));
            Pin(b.Glow.rectTransform, b.Fire, new Vector2(0.25f, 0.2f));
            b.Glow.transform.SetAsFirstSibling();   // under the trays' and the board's pins

            var wok = UIKit.Rect(art, "Wok" + k, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f));
            Pin(wok, b.Spot + new Vector3(0, 0.05f, 0), new Vector2(0.27f, 0.15f));
            var hit = wok.gameObject.AddComponent<Image>();
            hit.color = Color.clear;
            var btn = wok.gameObject.AddComponent<Button>();
            btn.transition = Selectable.Transition.None;
            btn.onClick.AddListener(() => TapBurner(k));
            for (int i = 0; i < 3; i++)
                b.Steam.Add(UIKit.Img(wok, "Steam" + i, UIKit.Circle, new Color(1, 1, 1, 0), new Vector2(0.22f + i * 0.2f, 0.5f), new Vector2(0.38f + i * 0.2f, 0.95f), preserveAspect: true));

            // on the front edge of its block, under the wok (above the woks is where the gauge's hint runs)
            var card = UIKit.Rect(art, "Card" + k, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f));
            Pin(card, b.Spot + new Vector3(-0.015f, -0.1f, -0.52f), new Vector2(0.205f, 0.07f));
            b.CardBg = UIKit.Panel(card, UIKit.Paper, false);
            b.CardBg.raycastTarget = true;
            var cardBtn = card.gameObject.AddComponent<Button>();
            cardBtn.transition = Selectable.Transition.None;
            cardBtn.onClick.AddListener(() => TapBurner(k));
            b.CardEdge = card.gameObject.AddComponent<Outline>();
            b.CardText = UIKit.Label(UIKit.Rect(card, "Text", Vector2.zero, Vector2.one), "", 22, UIKit.Ink, TextAnchor.MiddleCenter, FontStyle.Bold);
            // the 火候 bar: the needle's way across, the gold band in its middle, a tick where the needle is
            b.Bar = UIKit.Rect(card, "Bar", new Vector2(0.08f, 0.14f), new Vector2(0.92f, 0.36f));
            UIKit.Img(b.Bar, "Raw", null, Raw, Vector2.zero, Vector2.one);
            b.Gold = UIKit.Img(b.Bar, "Gold", null, Gold, new Vector2(0.4f, 0), new Vector2(0.6f, 1));
            b.Tick = UIKit.Img(b.Bar, "Tick", null, UIKit.Ink, new Vector2(0.5f, -0.35f), new Vector2(0.5f, 1.35f));
            b.Tick.rectTransform.sizeDelta = new Vector2(5, 0);
        }

        void BuildTop(Transform root)
        {
            // header: 烹饪 | the chosen dish (tap to change)
            var head = UIKit.Rect(root, "Header", new Vector2(0.015f, 0.875f), new Vector2(0.235f, 0.975f));
            UIKit.Button(head, null, 0, UIKit.Hex("#5a3d27"), Color.white, () => ShowPicker(true));
            UIKit.Label(UIKit.Rect(head, "Title", Vector2.zero, new Vector2(0.36f, 1)), "烹饪", 36, UIKit.Hex("#f4e2ae"), TextAnchor.MiddleCenter, FontStyle.Bold);
            var chip = UIKit.Rect(head, "Chip", new Vector2(0.38f, 0.12f), new Vector2(0.97f, 0.88f));
            UIKit.Panel(chip, UIKit.Paper, false).raycastTarget = false;
            headerDish = UIKit.Img(chip, "Pic", null, Color.white, new Vector2(0.02f, 0.02f), new Vector2(0.38f, 0.98f), preserveAspect: true);
            headerName = UIKit.Label(UIKit.Rect(chip, "Name", new Vector2(0.38f, 0), Vector2.one), "选菜 ▾", 30, UIKit.Ink, TextAnchor.MiddleCenter, FontStyle.Bold);

            // orders: a paper slip under the header
            var left = UIKit.Rect(root, "Orders", new Vector2(0.015f, 0.56f), new Vector2(0.2f, 0.86f));
            UIKit.Panel(left, new Color(UIKit.Paper.r, UIKit.Paper.g, UIKit.Paper.b, 0.9f));
            for (int i = 0; i < 6; i++)
            {
                var card = UIKit.Rect(left, "Order" + i, new Vector2(0, 1 - (i + 1) / 6.6f), new Vector2(1, 1 - i / 6.6f), new Vector2(10, 2), new Vector2(-10, -2));
                var img = UIKit.Panel(card, UIKit.Paper, false);
                var txt = UIKit.Label(card, "", 22, UIKit.Ink, TextAnchor.MiddleLeft);
                orderViews.Add((card, img, txt));
            }
            orderNote = UIKit.Label(UIKit.Rect(left, "Note", Vector2.zero, new Vector2(1, 0.1f)), "", 18, UIKit.InkSoft, TextAnchor.MiddleLeft);

            var back = UIKit.Rect(root, "Back", new Vector2(0.85f, 0.895f), new Vector2(0.985f, 0.975f));
            UIKit.Button(back, "返回前堂", 30, UIKit.Accent, Color.white, Close);
        }

        void BuildPicker(Transform root)
        {
            picker = UIKit.Rect(root, "Picker", Vector2.zero, Vector2.one);
            var dim = picker.gameObject.AddComponent<Image>();
            dim.color = new Color(0, 0, 0, 0.35f);
            picker.gameObject.AddComponent<Button>().onClick.AddListener(() => ShowPicker(false));
            var panel = UIKit.Rect(picker, "Panel", new Vector2(0.2f, 0.18f), new Vector2(0.8f, 0.86f));
            UIKit.Panel(panel, UIKit.Paper).raycastTarget = true;
            UIKit.Label(UIKit.Rect(panel, "Title", new Vector2(0, 0.86f), Vector2.one), "今天做什么菜", 40, UIKit.Ink, TextAnchor.MiddleCenter, FontStyle.Bold);
            var recipes = session.OpenRecipes().ToList();
            for (int i = 0; i < recipes.Count; i++)
            {
                var r = recipes[i];
                float w = 1f / Mathf.Max(3, recipes.Count);
                var card = UIKit.Rect(panel, "Card_" + r.Id, new Vector2(i * w, 0.04f), new Vector2((i + 1) * w, 0.86f), new Vector2(16, 0), new Vector2(-16, 0));
                UIKit.Button(card, null, 0, UIKit.Card, UIKit.Ink, () => { Select(r); ShowPicker(false); });
                UIKit.Img(card, "Pic", DishSprite(r.Id), Color.white, new Vector2(0.06f, 0.45f), new Vector2(0.94f, 0.97f), preserveAspect: true);
                UIKit.Label(UIKit.Rect(card, "Name", new Vector2(0, 0.34f), new Vector2(1, 0.46f)), r.Name, 36, UIKit.Ink, TextAnchor.MiddleCenter, FontStyle.Bold);
                var needs = r.Ingredients.Keys.Concat(r.Seasonings.Keys).Select(session.Data.IngredientName);
                UIKit.Label(UIKit.Rect(card, "Needs", new Vector2(0, 0.22f), new Vector2(1, 0.34f)), string.Join("·", needs), 22, UIKit.InkSoft);
                UIKit.Label(UIKit.Rect(card, "Info", new Vector2(0, 0.12f), new Vector2(1, 0.22f)), $"{r.CookMs / 1000f:0.#}秒·{r.Price / 100}文", 22, UIKit.InkSoft);
                var pending = UIKit.Label(UIKit.Rect(card, "Pending", new Vector2(0, 0.01f), new Vector2(0.5f, 0.12f)), "", 22, Burn, TextAnchor.MiddleCenter, FontStyle.Bold);
                var auto = UIKit.Label(UIKit.Rect(card, "Auto", new Vector2(0.5f, 0.01f), new Vector2(1, 0.12f)), "", 20, UIKit.InkSoft);
                pickerCards.Add((r, pending, auto));
            }
            picker.gameObject.SetActive(false);
        }

        /// <summary>Dish, ingredient or seasoning as a 三渲二 render of its 3D model (Resources/Food3D), else the flat art.</summary>
        static Sprite DishSprite(string id)
        {
            var s = Resources.Load<Sprite>("Food3D/" + id);
            return s != null ? s : Resources.Load<Sprite>("Food/" + id);
        }

        // ------------------------------------------------------------------ open / close

        public void Open()
        {
            if (IsOpen) return;
            IsOpen = true;
            setCam.enabled = true;
            canvas.gameObject.SetActive(true);
            fade = 0;
            group.alpha = 0;
            if (!session.Stoves[stoveIndex].Unlocked) stoveIndex = 0;
            // start on the dish the oldest order is waiting for, else keep the last choice
            var next = session.Service.Pending().FirstOrDefault();
            if (next.plate != null && (selected == null || session.PendingCount(selected) == 0)) Select(next.plate.Dish);
            else if (selected == null) ShowPicker(true);
        }

        public void Close()
        {
            if (!IsOpen) return;
            IsOpen = false;
            setCam.enabled = false;
            ShowPicker(false);
            canvas.gameObject.SetActive(false);
            Closed?.Invoke();
        }

        void ShowPicker(bool on) => picker.gameObject.SetActive(on);

        // ------------------------------------------------------------------ actions

        Stove ActiveStove => session.Stoves[stoveIndex];
        Burner Picked => burners[stoveIndex];

        void Select(Recipe r)
        {
            selected = r;
            headerDish.sprite = DishSprite(r.Id);
            headerName.text = r.Name + " ▾";
        }

        IEnumerable<string> Needs(Recipe r) => r.Ingredients.Keys.Concat(r.Seasonings.Keys);

        /// <summary>A block whose wok can take a dish now: open, not cooking, nothing waiting in it for 装盘.</summary>
        bool Free(Burner b) => session.Stoves[b.Index].State(GameSession.NowMs) == StoveState.Idle && session.InWok[b.Index] == null;

        /// <summary>
        /// The wok the chosen dish's next ingredient goes into: the picked one if it is free (and holds nothing of another
        /// dish), else a free one already holding some of this dish, else an empty one, else whichever is free (what of
        /// another dish was in it is taken back out). Null when every open wok is busy.
        /// </summary>
        Burner Target()
        {
            var free = burners.Where(Free).ToList();
            if (free.Count == 0) return null;
            bool Mine(Burner b) => b.PrepDish == selected && b.Prep.Count > 0;
            var picked = free.FirstOrDefault(b => b.Index == stoveIndex);
            if (picked != null && (Mine(picked) || picked.Prep.Count == 0)) return picked;
            return free.FirstOrDefault(Mine) ?? free.FirstOrDefault(b => b.Prep.Count == 0) ?? picked ?? free[0];
        }

        /// <summary>A tap on something on the board: into the wok it goes to (Target, then picked); once everything the
        /// dish needs is in, that wok starts.</summary>
        void TapItem(string id)
        {
            if (selected == null) { ShowPicker(true); return; }
            if (!Needs(selected).Contains(id)) { Toast($"{selected.Name}不用{session.Data.IngredientName(id)}", UIKit.Ink); return; }
            var b = Target();
            if (b == null) { Toast("锅都占着，先出锅或装盘", UIKit.Ink); return; }
            stoveIndex = b.Index;
            if (b.PrepDish != selected) { b.Prep.Clear(); b.PrepDish = selected; }
            b.Prep.Add(id);
            if (Needs(selected).All(b.Prep.Contains))
            {
                var res = session.Stoves[b.Index].Start(selected, GameSession.NowMs);
                if (res == Stove.StartResult.TierTooLow) Toast($"{selected.Name}要{CookRules.Name(selected.StoveTier)}", UIKit.Ink);
                b.Prep.Clear();
                b.PrepDish = null;
            }
        }

        /// <summary>
        /// A tap on a wok or its card: picks it (showing the dish being put together in it, if any); on the picked one,
        /// 出锅 while it cooks and 装盘 once it is out, as the button does. A wok whose needle is in the gold comes out at
        /// once and a finished dish goes onto a tray even before it is picked (with several woks going, a second tap
        /// would miss the gold). A closed block says when it opens.
        /// </summary>
        void TapBurner(int k)
        {
            var b = burners[k];
            var stove = session.Stoves[k];
            long now = GameSession.NowMs;
            if (!stove.Unlocked) { Toast($"升到「{OpensAt(k)}」开这口灶", UIKit.Ink); return; }
            var st = stove.State(now);
            bool ready = session.InWok[k] != null || st == StoveState.Cooking && CookRules.InGold(stove.Dish.Difficulty, stove.Needle(now));
            if (k != stoveIndex)
            {
                stoveIndex = k;
                if (ready) TapCook();
                else if (b.PrepDish != null && b.Prep.Count > 0) Select(b.PrepDish);
                return;
            }
            if (ready || st is StoveState.Cooking or StoveState.Burning) TapCook();
            else if (selected == null) ShowPicker(true);
        }

        /// <summary>The 声望 stage that opens block k (its short name: 一级②, 二级 …).</summary>
        string OpensAt(int k)
        {
            var stages = session.Data.Stages;
            var s = stages.FirstOrDefault(x => CookRules.StovesOpen(stages.IndexOf(x)) > k);
            return s == null ? "" : s.Name.Split(' ')[0];
        }

        /// <summary>The button under the wok: 出锅 while it cooks (judged by the needle; the dish stays in the wok,
        /// finished), then 装盘 (onto a free tray).</summary>
        void TapCook()
        {
            if (session.InWok[stoveIndex] != null)
            {
                if (!session.Plate(stoveIndex)) Toast("放置区满了，先把菜端出去", UIKit.Ink);
                return;
            }
            var s = ActiveStove;
            long now = GameSession.NowMs;
            var st = s.State(now);
            if (st == StoveState.Idle || st == StoveState.Locked)
            {
                bool other = burners.Any(b => b.Index != stoveIndex && (session.InWok[b.Index] != null ||
                                              session.Stoves[b.Index].State(now) is StoveState.Cooking or StoveState.Burning));
                Toast(other ? "先点那口锅，再出锅" : selected == null ? "先选一道菜" : "先把亮起来的食材和调味放进锅里", UIKit.Ink);
                return;
            }
            var r = session.TakeOut(s);
            resultText.text = CookRules.Name(r.q) + (r.q == Quality.Perfect || r.q == Quality.Immortal ? "！" : "");
            resultText.color = r.q switch
            {
                Quality.Immortal => UIKit.Hex("#e0a100"),
                Quality.Perfect => UIKit.Hex("#d9861c"),
                Quality.Good => Green,
                Quality.Burnt => Burn,
                _ => UIKit.InkSoft,
            };
            resultUntil = Time.unscaledTime + 1.6f;
            Picked.Result = resultText.text;
            Picked.ResultColor = resultText.color;
            Picked.ResultUntil = resultUntil;
            if (r.achievement != null) Toast($"成就「{r.achievement}」", UIKit.Good);
            if (r.autoUnlocked) Toast("这道菜你已经做熟了。以后点这道菜会自动做，同时最多占两口灶。", UIKit.Good);
        }

        void TapTray(int i)
        {
            bool discard = trayArmed == i && Time.unscaledTime < trayArmedUntil;
            var (msg, kept) = session.ServeTray(i, discard);
            if (msg == null) return;
            trayArmed = kept ? i : -1;
            trayArmedUntil = Time.unscaledTime + 1.8f;
            Toast(msg, kept ? UIKit.Ink : msg.Contains("端给") ? UIKit.Good : UIKit.InkSoft);
        }

        void Toast(string msg, Color bg)
        {
            toast.text = msg;
            toastBg.color = new Color(bg.r, bg.g, bg.b, 0.93f);
            toast.transform.parent.gameObject.SetActive(true);
            toastUntil = Time.unscaledTime + 1.8f;
        }

        // ------------------------------------------------------------------ for the screenshot run

        /// <summary>Choose the oldest ordered dish and put everything it needs into the wok.</summary>
        public bool DemoCookPending()
        {
            var next = session.Service.Pending().FirstOrDefault(x => !session.Trays.Any(t => t?.dish == x.plate.Dish));
            if (next.plate == null) return false;
            Select(next.plate.Dish);
            foreach (var id in Needs(selected).ToList()) TapItem(id);
            return true;
        }

        /// <summary>For the video: choose the oldest ordered dish not already on a tray; null when there is none.</summary>
        public Recipe DemoSelectPending()
        {
            var next = session.Service.Pending().FirstOrDefault(x => !session.Trays.Any(t => t?.dish == x.plate.Dish));
            if (next.plate == null) return null;
            Select(next.plate.Dish);
            return selected;
        }

        /// <summary>For the video: what the chosen dish needs from the board, in order.</summary>
        public List<string> DemoNeeds() => selected == null ? new List<string>() : Needs(selected).ToList();

        /// <summary>For the video: tap one thing on the board (it drops into the wok).</summary>
        public void DemoTap(string id) => TapItem(id);

        /// <summary>For the video: cook any dish at once, its raw ingredients straight into the wok (most dishes'
        /// ingredients have no place on this level's board), on a stove good enough for it.</summary>
        public void DemoShowcase(string dishId)
        {
            var r = session.Data.Recipes.FirstOrDefault(x => x.Id == dishId);
            if (r == null) return;
            Select(r);
            ShowPicker(false);   // as a card picked from it would
            Picked.Prep.Clear();
            Picked.PrepDish = null;
            ActiveStove.Tier = StoveTier.Advanced;
            ActiveStove.Start(r, GameSession.NowMs);
        }

        /// <summary>For the screenshots: pick block k (as a tap on its wok would) and, given a dish, cook it there at once.</summary>
        public void DemoCookOn(int k, string dishId = null)
        {
            if (k < 0 || k >= burners.Count || !session.Stoves[k].Unlocked) return;
            stoveIndex = k;
            if (dishId != null) DemoShowcase(dishId);
        }

        /// <summary>For the screenshots: choose a dish, as a card picked from the dish list would.</summary>
        public void DemoChoose(string dishId)
        {
            var r = session.Data.Recipes.FirstOrDefault(x => x.Id == dishId);
            if (r == null) return;
            Select(r);
            ShowPicker(false);
        }

        /// <summary>For the screenshots: how many blocks the set has.</summary>
        public int DemoBlocks => burners.Count;

        public bool DemoTraysFull() => session.FreeTray() < 0;

        /// <summary>For the video's run of the other dishes: no 端给/没人点 labels and badges on the trays.</summary>
        public bool DemoQuiet;

        /// <summary>For the video: the wok, and the middle of the trays, on the counter set.</summary>
        public Vector3 DemoWok => Picked.Axis;
        public Vector3 DemoTrays => (traySpots[0].pos + traySpots[traySpots.Count - 1].pos) / 2;

        /// <summary>For the video: the cook camera eased to `dist` metres from `target` along its own view (a close-up),
        /// or back where it stands (dist ≤ 0), over `seconds`.</summary>
        public System.Collections.IEnumerator DemoCloseUp(Vector3 target, float dist, float seconds)
        {
            var tr = setCam.transform;
            Vector3 a = tr.position, b = dist <= 0 ? camHome : target - tr.forward * dist;
            for (float t = 0; t < seconds; t += Time.unscaledDeltaTime)
            {
                tr.position = Vector3.Lerp(a, b, Mathf.SmoothStep(0f, 1f, t / seconds));
                yield return null;
            }
            tr.position = b;
        }

        /// <summary>For the video: clear the trays quietly (the showcase dishes have nobody to go to).</summary>
        public void DemoClearTrays()
        {
            for (int i = 0; i < GameSession.TrayCount; i++) session.Trays[i] = null;
        }

        public void DemoTakeOut() => TapCook();

        /// <summary>装盘 what is in the wok (the same button, once the dish is out).</summary>
        public void DemoPlate() => TapCook();

        public void DemoServeAll()
        {
            for (int i = 0; i < GameSession.TrayCount; i++) TapTray(i);
        }

        // ------------------------------------------------------------------ per frame

        void LateUpdate()
        {
            if (IsOpen) UpdatePins();
        }

        void Update()
        {
            if (!IsOpen) return;
            float t = Time.unscaledTime;
            if (fade < 1) { fade = Mathf.Min(1, fade + Time.unscaledDeltaTime / 0.18f); group.alpha = fade; }
            if (toast.transform.parent.gameObject.activeSelf && t > toastUntil) toast.transform.parent.gameObject.SetActive(false);
            if (UnityEngine.InputSystem.Keyboard.current?.escapeKey.wasPressedThisFrame == true) Close();
            long now = GameSession.NowMs;

            UpdateOrders(now);
            foreach (var (r, pending, auto) in pickerCards)
            {
                int n = session.PendingCount(r);
                pending.text = n > 0 ? $"待做 {n}" : "";
                auto.text = "自动做 " + session.Book.Progress(r);
            }

            // board: what the chosen dish needs lights up while a wok is free for it; what is in that wok is ticked
            var into = selected != null ? Target() : null;
            var needs = into != null ? Needs(selected).ToHashSet() : new HashSet<string>();
            var inWok = into != null && into.PrepDish == selected ? into.Prep : new HashSet<string>();
            foreach (var (id, img, ring, check, cg) in items)
            {
                img.enabled = false;   // the 3D food on the board is the picture
                bool need = needs.Contains(id), added = inWok.Contains(id);
                ring.enabled = need && !added;
                ring.transform.localScale = Vector3.one * (1f + 0.04f * Mathf.Sin(t * 5f));
                check.enabled = added;
                cg.alpha = need ? (added ? 0.55f : 1f) : 0.55f;
            }

            // trays: the 3D dish on each (burnt dishes stay as they were, darkened by the UI badge)
            for (int i = 0; i < trays.Count; i++)   // (not while the dish is still flying there from the wok)
            {
                var want = t < trayLandAt[i] ? null : session.Trays[i]?.dish.Id;
                if (want == trayModelIds[i]) continue;
                DestroyFood(trayModels[i]);
                trayModels[i] = want == null ? null : SpawnOnTray(want, i);
                trayModelIds[i] = want;
            }
            for (int i = 0; i < trays.Count; i++)
            {
                var (dish, label, badge, badgeText) = trays[i];
                var tray = session.Trays[i];
                dish.enabled = tray != null;
                badge.enabled = badgeText.enabled = tray != null && !DemoQuiet;
                label.transform.parent.gameObject.SetActive(tray != null && !DemoQuiet);
                if (tray == null) continue;
                var (rec, q) = tray.Value;
                dish.sprite = DishSprite(rec.Id);
                dish.enabled = false;   // the 3D dish sits on the tray instead
                dish.color = q == Quality.Burnt ? new Color(0.35f, 0.3f, 0.28f) : Color.white;
                badgeText.text = CookRules.Name(q);
                badge.color = q switch { Quality.Burnt => Burn, Quality.Underdone => UIKit.InkSoft, _ => Green };
                var target = session.Service.Pending().FirstOrDefault(x => x.plate.Dish.Id == rec.Id);
                label.text = q == Quality.Burnt ? "点击倒掉" : target.plate != null ? $"端给 {target.party.Table + 1} 号桌" : "没人点";
            }

            // every block: what is in its wok, its fire and lid, the steam, its card
            foreach (var b in burners) UpdateBurner(b, now, t);
            UpdateFlight();

            // the picked block: the gauge and the button
            var s = ActiveStove;
            var st = s.State(now);
            bool cooking = st is StoveState.Cooking or StoveState.Burning;
            var done = session.InWok[stoveIndex];
            UpdateGauge(s, st, now);
            resultText.enabled = t < resultUntil;

            cookButton.color = done != null ? Gold : cooking ? Green : UIKit.Locked;
            cookButtonText.text = done != null ? "装盘" : "出锅";
            autoPlateText.text = session.AutoPlate ? "自动装盘 ✓" : "自动装盘";
            autoPlateBg.color = session.AutoPlate ? UIKit.Hex("#cfe3a8") : PlaqueWood;
        }

        /// <summary>
        /// One block of the stove this frame: the lid on and the fire out while it is closed, the fire burning higher while
        /// it cooks, the picked wok glowing a little; in its wok (3D) the raw ingredients as they are tapped in, tossed
        /// about while the dish cooks, and from 出锅 the finished dish until 装盘 flies it to a tray; the glow of its fire,
        /// the steam over it, and its card.
        /// </summary>
        void UpdateBurner(Burner b, long now, float t)
        {
            var stove = session.Stoves[b.Index];
            var st = stove.State(now);
            bool open = stove.Unlocked, cooking = st is StoveState.Cooking or StoveState.Burning;
            var done = session.InWok[b.Index];
            foreach (var r in b.Lid) r.enabled = !open;
            if (b.FireCard)
            {
                float lit = !open ? 0.32f : cooking ? 1f : 0.78f;
                b.FireCard.GetPropertyBlock(mpb);
                mpb.SetColor(TintId, new Color(lit, lit, lit, 1f));
                mpb.SetFloat(FlickerId, cooking ? 1f : open ? 0.35f : 0f);
                b.FireCard.SetPropertyBlock(mpb);
            }
            float glow = open && b.Index == stoveIndex && burners.Count(x => session.Stoves[x.Index].Unlocked) > 1
                ? 0.14f + 0.08f * Mathf.Sin(t * 4f) : 0f;
            foreach (var r in b.Wok)
            {
                r.GetPropertyBlock(mpb);
                mpb.SetFloat(HighlightId, glow);
                r.SetPropertyBlock(mpb);
            }

            var raw = cooking ? stove.Dish.Ingredients.Keys.ToList()
                : st == StoveState.Idle && done == null && b.PrepDish != null
                    ? b.PrepDish.Ingredients.Keys.Where(b.Prep.Contains).ToList() : new List<string>();
            UpdateRaw(b, raw, cooking, st == StoveState.Burning, t);
            UpdateDone(b, done, t);

            b.Glow.color = new Color(1f, 0.62f, 0.2f, cooking ? 0.14f + 0.06f * Mathf.Sin(t * 9f + b.Index) : 0f);
            b.Glow.transform.localScale = Vector3.one * (cooking ? 1.1f + 0.08f * Mathf.Sin(t * 13f + b.Index) : 1f);
            bool puff = done != null && t - b.DoneSince < 0.8f;   // a burst of steam as the dish comes out
            for (int i = 0; i < b.Steam.Count; i++)
            {
                float ph = (t * (puff ? 1.4f : 0.6f) + i / 3f + b.Index * 0.29f) % 1f;
                float a = puff ? 0.6f : done != null ? 0.18f : !cooking ? 0 : st == StoveState.Burning ? 0.55f : 0.35f;
                b.Steam[i].color = st == StoveState.Burning ? new Color(0.35f, 0.33f, 0.32f, a * (1 - ph)) : new Color(1, 1, 1, a * (1 - ph));
                b.Steam[i].rectTransform.anchoredPosition = new Vector2(Mathf.Sin(t * 2 + i) * 5f, ph * 50f);
            }
            UpdateCard(b, stove, st, done, now, t);
        }

        /// <summary>
        /// The card over a wok: closed (and the stage that opens it), empty, the dish going in (how much of it is in),
        /// cooking (its name over a small 火候 bar, the card turning gold while the needle is in the band), burnt, or out
        /// and waiting for 装盘; for a moment after 出锅 the result. The picked block's card is edged in gold.
        /// </summary>
        void UpdateCard(Burner b, Stove stove, StoveState st, (Recipe dish, Quality q, long atMs)? done, long now, float t)
        {
            string text;
            Color bg = UIKit.Paper, fg = UIKit.Ink;
            bool bar = false;
            if (!stove.Unlocked) { text = $"「{OpensAt(b.Index)}」开"; bg = UIKit.Locked; fg = UIKit.InkSoft; }
            else if (t < b.ResultUntil) { text = b.Result; bg = b.ResultColor; fg = Color.white; }
            else if (done is { } d) { text = $"{d.dish.Name}·装盘"; bg = Gold; }
            else if (st == StoveState.Burning) { text = "糊了！"; bg = Burn; fg = Color.white; }
            else if (st == StoveState.Cooking)
            {
                text = stove.Dish.Name;
                bar = true;
                double p = stove.Needle(now);
                float w = (float)CookRules.GoldHalfWidth(stove.Dish.Difficulty);
                b.Gold.rectTransform.anchorMin = new Vector2(0.5f - w, 0);
                b.Gold.rectTransform.anchorMax = new Vector2(0.5f + w, 1);
                b.Tick.rectTransform.anchorMin = new Vector2((float)p, -0.35f);
                b.Tick.rectTransform.anchorMax = new Vector2((float)p, 1.35f);
                if (CookRules.InGold(stove.Dish.Difficulty, p)) bg = UIKit.Hex("#f7dc94");
            }
            else if (b.PrepDish != null && b.Prep.Count > 0) text = $"{b.PrepDish.Name} {b.Prep.Count}/{Needs(b.PrepDish).Count()}";
            else { text = "空着"; fg = UIKit.InkSoft; }
            b.CardText.text = text;
            b.CardText.color = fg;
            b.CardBg.color = bg;
            var tr = b.CardText.rectTransform;
            tr.anchorMin = new Vector2(0, bar ? 0.36f : 0f);
            b.Bar.gameObject.SetActive(bar);
            bool picked = b.Index == stoveIndex && stove.Unlocked;
            b.CardEdge.effectColor = picked ? UIKit.Hex("#d9861c") : new Color(UIKit.Ink.r, UIKit.Ink.g, UIKit.Ink.b, 0.45f);
            b.CardEdge.effectDistance = picked ? new Vector2(3, -3) : new Vector2(1.5f, -1.5f);
        }

        // ------------------------------------------------------------------ the wok

        /// <summary>The wok's inside as build_cook_view.py turns it, (distance from its axis, height over its bottom), in
        /// metres for a wok 0.36 m across its outside radius; each block's wok is measured against it (MeasureSet).</summary>
        static readonly Vector2[] WokProfile = { new(0f, 0f), new(0.16f, 0.02f), new(0.31f, 0.11f), new(0.345f, 0.155f) };
        const int MaxRawPieces = 9;   // pieces in a wok at once
        readonly List<Bounds> trayRooms = new();   // the inside of each tray, its floor at the bottom
        Bounds boardRoom;
        JObject rawPieces;            // Resources/raw_pieces.json (build_raw.py): per ingredient, its pieces

        /// <summary>The woks and the trays measured from the set itself, so that the food is fitted into them; each block's
        /// wok, lid and fire mouth found by name.</summary>
        void MeasureSet()
        {
            var rends = setRoot.GetComponentsInChildren<Renderer>(true);
            Renderer Find(string n) => rends.FirstOrDefault(r => r.name == n);
            foreach (var bl in burners)
            {
                int k = bl.Index;
                var wok = Find("Wok" + k) ?? (k == 0 ? Find("Wok") : null);
                if (wok)
                {
                    var b = wok.bounds;
                    bl.K = b.extents.x / 0.36f;
                    bl.Axis = new Vector3(b.center.x, b.min.y + 0.02f * bl.K, b.center.z);
                }
                else bl.Axis = bl.Spot - Vector3.up * 0.04f;
                bl.Wok = rends.Where(r => r == wok || r.name.StartsWith($"WokHandle{k}_")).ToArray();
                bl.Lid = rends.Where(r => r.name == "Lid" + k).ToArray();
                bl.FireCard = Find("FireMouth" + k) ?? (k == 0 ? Find("FireMouth") : null);
            }
            for (int i = 0; i < GameSession.TrayCount; i++)
            {
                var tr = Find("Tray" + i);
                trayRooms.Add(tr ? Room(tr.bounds, 0.04f) : new Bounds(traySpots[i].pos + Vector3.up * 0.25f, new Vector3(0.46f, 0.5f, 0.33f)));
            }
            var bd = Find("Board");
            boardRoom = bd ? Room(bd.bounds, 0.035f) : new Bounds(Vector3.zero, Vector3.zero);
            var json = Resources.Load<TextAsset>("raw_pieces");
            rawPieces = json ? JObject.Parse(json.text) : new JObject();
        }

        /// <summary>The room inside a tray (its rims `rim` wide), its floor the tray's top.</summary>
        static Bounds Room(Bounds tray, float rim) =>
            new(new Vector3(tray.center.x, tray.max.y + 0.25f, tray.center.z),
                new Vector3(tray.size.x - 2 * rim, 0.5f, tray.size.z - 2 * rim));

        /// <summary>How high a wok's inside is this far from its axis, over its bottom.</summary>
        static float WokHeight(Burner bl, float r)
        {
            r = Mathf.Abs(r) / bl.K;
            for (int i = 1; i < WokProfile.Length; i++)
                if (r <= WokProfile[i].x)
                {
                    var a = WokProfile[i - 1];
                    var b = WokProfile[i];
                    return Mathf.Lerp(a.y, b.y, (r - a.x) / (b.x - a.x)) * bl.K;
                }
            return WokProfile[WokProfile.Length - 1].y * bl.K;
        }

        /// <summary>
        /// The ingredients on the board, each in its own place: the board split into its back row (the ingredients) and
        /// its front row (the seasonings), each row into places halfway between neighbours; each item stands in the middle
        /// of its place, made smaller only if it is bigger than its place, so that none goes into another or over the
        /// board's rims.
        /// </summary>
        void SettleOnBoard(List<GameObject> gos)
        {
            if (boardRoom.size.x <= 0 || gos.Count == 0) return;
            var at = gos.Select(g => g.transform.position).ToList();
            float split = (at.Min(p => p.z) + at.Max(p => p.z)) / 2;            // between the two rows of spots
            float mid = boardRoom.min.z + boardRoom.size.z * 0.45f;             // the back row gets a little more depth
            for (int i = 0; i < gos.Count; i++)
            {
                bool back = at[i].z > split;
                var row = Enumerable.Range(0, gos.Count).Where(j => (at[j].z > split) == back).Select(j => at[j].x).OrderBy(x => x).ToList();
                int k = row.IndexOf(at[i].x);
                float x0 = k == 0 ? boardRoom.min.x : (row[k - 1] + row[k]) / 2;
                float x1 = k == row.Count - 1 ? boardRoom.max.x : (row[k] + row[k + 1]) / 2;
                float z0 = back ? mid : boardRoom.min.z, z1 = back ? boardRoom.max.z : mid;
                var cell = new Bounds(new Vector3((x0 + x1) / 2, boardRoom.min.y + 0.25f, (z0 + z1) / 2),
                                      new Vector3((x1 - x0) * 0.94f, 0.5f, (z1 - z0) * 0.94f));
                FoodFit.FitIn(gos[i], cell);
            }
        }

        /// <summary>How many pieces of an ingredient go into the wok, and whether it goes in whole (a fish, a crab);
        /// none for what has no piece of its own (the seasonings, cooked into the dish unseen).</summary>
        (int count, bool whole) RawCount(string id)
        {
            var e = rawPieces[id];
            if (e == null) return (Resources.Load<GameObject>("FoodModels/RAW_" + id) ? 3 : 0, false);
            int n = e["count"] != null ? (int)e["count"] : 3;
            float size = e["size"] != null ? (float)e["size"] : 0.05f;
            return (Mathf.Max(1, n), n == 1 && size >= 0.15f);
        }

        /// <summary>A raw piece for the wok (Resources/FoodModels/RAW_&lt;id&gt;: one closed, solid piece, true to
        /// size, its pivot at its foot), as big as it is.</summary>
        GameObject SpawnRaw(Burner bl, string id)
        {
            var prefab = Resources.Load<GameObject>("FoodModels/RAW_" + id);
            if (prefab == null) return null;
            var go = Instantiate(prefab, bl.Axis, prefab.transform.rotation, setRoot);
            go.name = "Raw_" + id;
            return go;
        }

        /// <summary>One raw piece in the wok: which it is, how big it is made, where it rests (on the wok's inside,
        /// leaning with it), how high it stands (it turns about its middle in the air), the level axis it turns over
        /// about and how far it swings out from it, and its seed (its hops are out of step with the others').</summary>
        class RawPiece
        {
            public GameObject go;
            public string id;
            public int j;              // which of its ingredient's pieces
            public bool whole;         // a whole fish or crab, in the middle
            public float reach0;       // how far it reaches from its middle, as big as it is
            public Vector3 scale0;     // its scale then
            public float reach;        // how far it reaches in the wok
            public Vector3 home;
            public Quaternion pose;
            public float half;
            public Vector3 roll;
            public float swing;
            public int seed;
        }

        /// <summary>
        /// The raw ingredients laid out in the wok, each ingredient as its pieces (raw_pieces.json; at most
        /// MaxRawPieces in all), each as big as it is, made larger so that it reads in the kitchen's view: a whole
        /// fish or crab a little larger, in the middle; the small pieces (a chunk of pork, a chili, a leaf) two and a
        /// half times, no bigger than the wok can toss, round it on a ring, each given room along the ring for its own
        /// width, the ingredients mixed. If they would crowd past the wok's floor, all the small ones are made a little
        /// smaller alike. Each rests on the wok's curved inside, leaning with it and lifted where the curve rises under
        /// its ends, so that nothing goes through the wok or through another piece. Pieces already in the wok move
        /// over as others come.
        /// </summary>
        void LayOutRaw(Burner bl, List<string> ids)
        {
            var raw = bl.Raw;
            float wokK = bl.K;
            var wokAxis = bl.Axis;
            float WokHeight(float r) => CookingScreen.WokHeight(bl, r);
            var want = ids.Select(id => (id, c: RawCount(id))).Where(w => w.c.count > 0)
                          .Select(w => (w.id, n: w.c.count, w.c.whole)).ToList();
            while (want.Sum(w => w.n) > MaxRawPieces && want.Any(w => w.n > 1))   // the most plentiful give way first
            {
                int k = want.FindIndex(w => w.n == want.Max(x => x.n));
                want[k] = (want[k].id, want[k].n - 1, want[k].whole);
            }
            var old = raw.ToList();
            raw.Clear();
            foreach (var w in want)
                for (int j = 0; j < w.n; j++)
                {
                    var p = old.FirstOrDefault(o => o.go && o.id == w.id && o.j == j);
                    if (p != null) { old.Remove(p); raw.Add(p); continue; }
                    var go = SpawnRaw(bl, w.id);
                    if (go == null) continue;
                    raw.Add(new RawPiece
                    {
                        go = go, id = w.id, j = j, whole = w.whole, seed = j + 16 * ((w.id.GetHashCode() & 0x7fff) % 97),
                        reach0 = Mathf.Max(FoodFit.Footprint(go).reach, 1e-3f), scale0 = go.transform.localScale,
                    });
                }
            foreach (var o in old)
                if (o.go) Destroy(o.go);

            var wholes = raw.Where(p => p.whole).ToList();
            var small = raw.Where(p => !p.whole).OrderBy(p => p.j).ThenBy(p => p.id).ToList();   // mixed round the ring
            foreach (var p in wholes) p.reach = Mathf.Min(p.reach0 * 1.3f, (wholes.Count == 1 ? 0.17f : 0.11f) * wokK);
            foreach (var p in small) p.reach = Mathf.Min(p.reach0 * 2.6f, 0.075f * wokK);
            // the ring: clear of what lies in the middle, long enough for every piece and the gaps, within the floor
            float gap = 0.012f * wokK, rMax = 0.25f * wokK, ring = 0f;
            float inner = wholes.Count == 0 ? 0f : wholes.Count == 1 ? wholes[0].reach : 0.09f * wokK + wholes.Max(p => p.reach);
            if (small.Count > 1 || small.Count == 1 && wholes.Count > 0)
            {
                float most = small.Max(p => p.reach), across = small.Sum(p => 2 * p.reach);
                float k = Mathf.Clamp(Mathf.Min((rMax - inner - gap) / most, (2 * Mathf.PI * rMax - small.Count * gap) / across), 0.3f, 1f);
                foreach (var p in small) p.reach *= k;
                ring = Mathf.Max(inner + most * k + gap, (across * k + small.Count * gap) / (2 * Mathf.PI));
            }

            void Place(RawPiece p, float r, float ang)
            {
                var go = p.go;
                bool fresh = p.half == 0f;   // just spawned: it drops in from above
                go.transform.localScale = p.scale0 * (p.reach / p.reach0);
                var dir = new Vector3(Mathf.Cos(ang), 0, Mathf.Sin(ang));
                // the wok's inside here: its height, its slope and its normal; the piece leans with it
                float h = WokHeight(r), slope = (WokHeight(r + 0.005f) - WokHeight(Mathf.Max(r - 0.005f, 0f))) / 0.01f;
                var n = (Vector3.up - dir * slope).normalized;
                p.pose = fresh ? Quaternion.FromToRotation(Vector3.up, n) * Quaternion.Euler(0, p.seed * 47f % 360f, 0) * go.transform.rotation
                               : Quaternion.FromToRotation(p.pose * Vector3.up, n) * p.pose;
                // lifted where the wok's curve rises above the slope under the piece's ends (its inside is convex)
                float lift = 0f;
                for (float s = -p.reach; s <= p.reach; s += p.reach / 6f)
                    lift = Mathf.Max(lift, WokHeight(r + s) - (h + slope * s));
                p.home = wokAxis + dir * r + Vector3.up * h + n * (lift + 0.004f);
                // posed where it rests: how high it stands, and how it turns over in the air
                var was = (go.transform.position, go.transform.rotation);
                go.transform.SetPositionAndRotation(p.home, p.pose);
                p.half = (FoodFit.Bounds(go).max.y - FoodFit.Footprint(go).bottom) / 2;
                if (p.whole)
                {   // a whole fish or crab rolls over about its length, as it is turned in a wok
                    var hull = FoodFit.Hull(go);
                    Vector2 q0 = Vector2.zero, q1 = Vector2.right;
                    float best = -1f;
                    for (int i = 0; i < hull.Count; i++)
                        for (int k = i + 1; k < hull.Count; k++)
                        {
                            float d = (hull[i] - hull[k]).sqrMagnitude;
                            if (d > best) { best = d; q0 = hull[i]; q1 = hull[k]; }
                        }
                    var along = (q1 - q0).normalized;
                    var side = new Vector2(-along.y, along.x);
                    float wide = 0f;
                    foreach (var q in hull) wide = Mathf.Max(wide, Mathf.Abs(Vector2.Dot(q - (q0 + q1) / 2, side)));
                    p.roll = new Vector3(along.x, 0f, along.y);
                    p.swing = Mathf.Sqrt(wide * wide + p.half * p.half);
                }
                else
                {   // a small piece turns about the way out from the wok's middle: its ends move along the ring, neither
                    // into the wok's rising side nor out to a neighbour (in the middle: any level way)
                    p.roll = r > 0.001f ? dir : Quaternion.Euler(0, p.seed * 31f, 0) * Vector3.right;
                    p.swing = Mathf.Max(p.reach, p.half);
                }
                if (fresh) go.transform.position = p.home + Vector3.up * 0.35f;   // dropped in from above
                else go.transform.SetPositionAndRotation(was.Item1, was.Item2);
            }
            for (int i = 0; i < wholes.Count; i++)
                Place(wholes[i], wholes.Count == 1 ? 0f : 0.09f * wokK, i * Mathf.PI);
            // round the ring, each piece an arc as wide as it is, what is left over shared out between them
            float spare = ring > 0f ? 2 * Mathf.PI - small.Sum(p => (2 * p.reach + gap) / ring) : 0f;
            float at = 0.6f;
            foreach (var p in small)
            {
                float arc = ring > 0f ? (2 * p.reach + gap) / ring + Mathf.Max(spare, 0f) / small.Count : 0f;
                Place(p, ring, at + arc / 2);
                at += arc;
            }
        }

        /// <summary>The raw ingredients in the wok: each piece drops in when its ingredient is added; while the dish
        /// cooks they are stir-fried, hopping up in turn, turning over in the air (solid pieces, so every side is
        /// real), each hop high enough for it to turn right over clear of the wok, and landing back where they lay.</summary>
        void UpdateRaw(Burner bl, List<string> ids, bool tossing, bool burning, float t)
        {
            var key = string.Join(",", ids);
            if (key != bl.RawKey)
            {
                LayOutRaw(bl, ids);
                bl.RawKey = key;
            }
            float wokK = bl.K;
            float T = burning ? 1.3f : 0.9f;   // one hop; slower once it burns
            foreach (var p in bl.Raw)
            {
                if (!p.go) continue;
                var tr = p.go.transform;
                if (!tossing)
                {   // dropping in, then lying still
                    tr.rotation = p.pose;
                    tr.position = Vector3.Lerp(tr.position, p.home, 1f - Mathf.Exp(-Time.unscaledDeltaTime * 12f));
                    continue;
                }
                float ph = t / T + p.seed * 0.137f;
                int hop = Mathf.FloorToInt(ph);
                float tau = ph - hop, air = 0.6f;
                bool over = (p.seed + hop) % 2 == 0;   // a whole turn every other hop, else it rocks
                float h = 0f, e = 1f;
                if (tau < air)
                {
                    float s = tau / air;
                    float top = (0.07f + 0.025f * ((p.seed + hop) % 3)) * wokK;
                    if (over) top = Mathf.Max(top, 1.3f * p.swing + 0.012f * wokK);   // its ends swing out as far as that
                    h = top * 4f * s * (1 - s);
                    e = s * s * (3 - 2 * s);
                }
                float spin = tau < air ? (over ? 360f * e : 30f * Mathf.Sin(tau / air * Mathf.PI)) : 0f;
                var turn = Quaternion.AngleAxis(p.seed % 2 == 0 ? spin : -spin, p.roll);
                var up = p.pose * Vector3.up * p.half;   // from its foot to its middle
                tr.rotation = turn * p.pose;
                tr.position = p.home + up + Vector3.up * h - turn * up;
            }
        }

        /// <summary>From 出锅 until 装盘: the finished dish in the wok (SM_&lt;dish&gt;_wok), scaled to fit inside it and bent
        /// to the curve of its inside so that nothing goes through it, popping in as the raw pieces go.</summary>
        void UpdateDone(Burner bl, (Recipe dish, Quality q, long atMs)? done, float t)
        {
            string id = done == null ? null : done.Value.dish.Id + "_wok";
            if (id != bl.DoneId)
            {
                DestroyFood(bl.Done);
                bl.Done = id == null ? null : SpawnFood(id, bl.Axis, bl.Scale, 0) ?? SpawnFood(done.Value.dish.Id, bl.Axis, bl.Scale, 0);
                if (bl.Done)
                {
                    var f = FoodFit.Footprint(bl.Done);
                    float fit = 0.24f * bl.K;   // its reach: well inside the wok's wall
                    if (f.reach > fit) FoodFit.ScaleAbout(bl.Done, f.middle, fit / f.reach);
                    f = FoodFit.Footprint(bl.Done);
                    bl.Done.transform.position += new Vector3(bl.Axis.x - f.middle.x, bl.Axis.y + 0.004f - f.bottom, bl.Axis.z - f.middle.z);
                    FoodFit.BendInto(bl.Done, bl.Axis, r => WokHeight(bl, r));
                    bl.DoneScale = bl.Done.transform.localScale;
                }
                bl.DoneId = id;
                bl.DoneSince = t;
            }
            if (!bl.Done) return;
            float u = t - bl.DoneSince;   // swells in, overshoots a little and settles
            float k = u < 0.12f ? Mathf.Lerp(0.55f, 1.06f, u / 0.12f)
                : u < 0.45f ? Mathf.Lerp(1.06f, 1f, (u - 0.12f) / 0.33f) : 1f;
            bl.Done.transform.localScale = bl.DoneScale * k;
        }

        /// <summary>Destroys a placed dish and the bent copies of its meshes.</summary>
        static void DestroyFood(GameObject go)
        {
            if (!go) return;
            foreach (var mf in go.GetComponentsInChildren<MeshFilter>())
                if (mf.sharedMesh && mf.sharedMesh.name.EndsWith("(bent)")) Destroy(mf.sharedMesh);
            Destroy(go);
        }

        /// <summary>A dish on tray i: as big as the tray's inside holds (made smaller if it is bigger, larger if it is
        /// smaller, so that every dish reads alike), resting on its floor, clear of its rims.</summary>
        GameObject SpawnOnTray(string id, int i)
        {
            var go = SpawnFood(id, trayRooms[i].center, traySpots[i].scale * 0.85f, 0);
            if (go) FoodFit.FitIn(go, trayRooms[i], grow: 1.6f);
            return go;
        }

        /// <summary>装盘: the dish flies from its wok to its tray in an arc, growing into its plate.</summary>
        void OnPlated(int stove, int tray)
        {
            if (!IsOpen || stove >= burners.Count || session.Trays[tray] == null) return;
            if (flying) Destroy(flying);
            flying = SpawnOnTray(session.Trays[tray].Value.dish.Id, tray);   // where it lands, as big as it lands
            if (!flying) return;
            flyTo = flying.transform.position;
            flyScale1 = flying.transform.localScale;
            flyScale0 = flyScale1 * 0.75f;
            flyFrom = burners[stove].Axis + Vector3.up * 0.06f;
            flyStart = Time.unscaledTime;
            trayLandAt[tray] = flyStart + FlySeconds;
            UpdateFlight();
        }

        void UpdateFlight()
        {
            if (!flying) return;
            float u = Mathf.Clamp01((Time.unscaledTime - flyStart) / FlySeconds);
            float e = u * u * (3 - 2 * u);
            flying.transform.position = Vector3.Lerp(flyFrom, flyTo, e) + Vector3.up * Mathf.Sin(u * Mathf.PI) * 0.45f;
            flying.transform.localScale = Vector3.Lerp(flyScale0, flyScale1, e);
            if (u >= 1f) { Destroy(flying); flying = null; }
        }

        void UpdateGauge(Stove s, StoveState st, long now)
        {
            if (session.InWok[stoveIndex] is { } out_)
            {   // 出锅了: the gauge rests; the hint says what next
                needle.rectTransform.parent.localRotation = Quaternion.Euler(0, 0, 90);
                timeBar.fillAmount = 0;
                gaugeHint.text = session.AutoPlate ? $"{out_.dish.Name}出锅了·马上自动装盘" : $"{out_.dish.Name}出锅了·点「装盘」放到放置区";
                return;
            }
            Recipe dish = st == StoveState.Idle ? selected : s.Dish;
            if (dish == null)
            {
                foreach (var z in gaugeZones) z.fillAmount = 0;
                needle.rectTransform.parent.localRotation = Quaternion.Euler(0, 0, 90);
                gaugeHint.text = "点左上角选菜";
                timeBar.fillAmount = 0;
                return;
            }
            float w = (float)CookRules.GoldHalfWidth(dish.Difficulty), iw = (float)CookRules.ImmortalHalfWidth;
            bool core = dish.Difficulty >= 3;
            gaugeZones[0].fillAmount = 1f;
            gaugeZones[1].fillAmount = 0.5f + w;
            gaugeZones[2].fillAmount = core ? 0.5f + iw : 0f;
            gaugeZones[3].fillAmount = core ? 0.5f - iw : 0f;
            gaugeZones[4].fillAmount = 0.5f - w;
            bool burning = st == StoveState.Burning;
            gaugeZones[0].color = gaugeZones[4].color = burning ? UIKit.Hex("#e7b3a4") : Raw;
            gaugeZones[1].color = gaugeZones[3].color = burning ? Burn : Gold;

            double p = st is StoveState.Cooking or StoveState.Burning ? s.Needle(now) : 0.0;
            needle.rectTransform.parent.localRotation = Quaternion.Euler(0, 0, 90f - 180f * (float)p);
            float limit = CookRules.GraceMs + dish.CookMs;
            timeBar.fillAmount = st == StoveState.Cooking ? Mathf.Clamp01(s.LeftMs(now) / limit) : st == StoveState.Idle ? 1f : 0f;
            timeBar.color = timeBar.fillAmount > 0.35f ? Green : UIKit.Fire;
            gaugeHint.text = st switch
            {
                StoveState.Idle => $"放齐食材就开火·{limit / 1000f:0.#} 秒内出锅",
                StoveState.Cooking => $"指针在金色里出锅就是完美·还剩 {CookRules.Seconds(s.LeftMs(now))} 秒",
                StoveState.Burning => "糊了！快出锅倒掉",
                _ => "",
            };
        }

        /// <summary>For the screenshot run: is the needle in the gold band right now?</summary>
        public bool NeedleInGold()
        {
            var s = ActiveStove;
            return s.Dish != null && CookRules.InGold(s.Dish.Difficulty, s.Needle(GameSession.NowMs));
        }

        void UpdateOrders(long now)
        {
            var rows = new List<(string text, Color bg, Color fg)>();
            foreach (var p in session.Service.Parties)
            {
                if (p.State == PartyState.Waiting)
                {
                    long left = p.OrderedMs + p.PatienceMs - now;
                    var head = p.Late ? $"{p.Table + 1} 号桌 催单！{CookRules.Seconds(p.LeaveAtMs - now)}秒"
                                      : $"{p.Table + 1} 号桌·耐心 {CookRules.Seconds(left)}秒";
                    rows.Add((head, p.Late ? UIKit.Hex("#f2c6b4") : UIKit.CardDark, p.Late ? Burn : UIKit.Ink));
                    foreach (var g in p.Plates.GroupBy(pl => pl.Dish.Name))
                    {
                        int served = g.Count(pl => pl.Served), all = g.Count();
                        rows.Add(($"　{g.Key}{(all > 1 ? $" ×{all}" : "")}{(served == all ? "　✓" : served > 0 ? $"　{served}/{all}" : "")}",
                                  served == all ? UIKit.Hex("#e4efc9") : UIKit.Paper, served == all ? UIKit.InkSoft : UIKit.Ink));
                    }
                }
                else if (p.State == PartyState.Dining)
                    rows.Add(($"{p.Table + 1} 号桌·用餐中", UIKit.Hex("#e4efc9"), Green));
            }
            for (int i = 0; i < orderViews.Count; i++)
            {
                var (card, img, text) = orderViews[i];
                card.gameObject.SetActive(i < rows.Count);
                if (i >= rows.Count) continue;
                text.text = rows[i].text;
                img.color = rows[i].bg;
                text.color = rows[i].fg;
            }
            orderNote.text = session.Day.Phase != DayPhase.Service ? "  开门营业后客人才会来"
                : rows.Count == 0 ? "  暂时没有客人点单" : "";
        }
    }
}
