using System;
using System.Collections.Generic;
using System.Linq;
using BianHe.Core;
using UnityEngine;
using UnityEngine.UI;

namespace BianHe
{
    /// <summary>
    /// 做饭界面, laid out after the 烹饪 mock-up (eg.jpg): a first-person view of the kitchen counter in
    /// three parts — 放置区 (trays for finished dishes), 食材与调味 (the board), 灶台 (wok, fire and
    /// the 火候 gauge) — with the chosen dish top left and 出锅 bottom right.
    ///
    /// Play: pick a dish → tap what it needs on the board (it lights up) → the wok starts once everything
    /// is in → tap 出锅 while the needle is in the gold band → tap the tray to carry the dish to its table.
    /// The gauge shows CookRules: the needle swings over a gold band; within the time limit (cook time
    /// + 3 s) gold is 完美 and anywhere else 没熟, and after the limit it's 糊了. Stoves keep cooking
    /// while the screen is closed. The room, counter, trays, stove and wok are the painted layers
    /// The room, counter, trays, stove and wok are a 3D set (CookSet.fbx, built by build_cook_view.py
    /// --export in the approved 水彩 style) seen through its own camera; the food on it is 3D too. The
    /// UI is pinned over the set's markers (Resources/cook_set.json) every frame.
    /// </summary>
    public class CookingScreen : MonoBehaviour
    {
        public event Action Closed;
        public bool IsOpen { get; private set; }

        GameSession session;
        Canvas canvas;
        CanvasGroup group;
        Recipe selected;
        int stoveIndex;
        readonly HashSet<string> prep = new();   // what is already in the wok for the dish being set up

        // views
        Image headerDish;
        Text headerName;
        RectTransform picker;
        readonly List<(Recipe r, Text pending, Text auto)> pickerCards = new();
        readonly List<(string id, Image img, Image ring, Text check, CanvasGroup cg)> items = new();
        readonly List<(Image dish, Text label, Image badge, Text badgeText)> trays = new();
        readonly List<(RectTransform card, Image img, Text text)> orderViews = new();
        Text orderNote, stoveLabel, gaugeHint, resultText, cookButtonText;
        Image wokFood, fireGlow, needle, cookButton;
        readonly List<Image> wokItems = new();
        readonly List<Image> steam = new();
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
        (Vector3 pos, float scale) wokSpot;
        readonly GameObject[] trayModels = new GameObject[GameSession.TrayCount];
        readonly string[] trayModelIds = new string[GameSession.TrayCount];
        GameObject wokModel;
        string wokModelId;
        readonly List<GameObject> prepModels = new();
        string prepKey = "";

        static readonly string[] SeasoningOrder = { "salt", "oil", "scallion", "ginger" };   // 糖 joins when a dish needs it

        // Where things are in the backdrop art (背景.png / 案台 (2).png, 1672 × 941), as fractions of the
        // picture with y measured from the bottom. Everything that sits on the art is placed with these.
        const float ArtAspect = 1672f / 941f;
        static readonly Rect[] TrayArt =
        {
            Rect.MinMaxRect(0.060f, 0.325f, 0.164f, 0.44f), Rect.MinMaxRect(0.157f, 0.325f, 0.260f, 0.44f),
            Rect.MinMaxRect(0.260f, 0.325f, 0.365f, 0.44f),
        };
        static readonly Rect BoardArt = Rect.MinMaxRect(0.388f, 0.30f, 0.652f, 0.53f);    // the big tray (食材与调味)
        static readonly Rect WokArt = Rect.MinMaxRect(0.735f, 0.425f, 0.88f, 0.55f);     // inside of the wok
        static readonly Rect FireArt = Rect.MinMaxRect(0.768f, 0.09f, 0.878f, 0.235f);   // fire mouth

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
            fireGlow = UIKit.Img(pinLayer, "FireGlow", UIKit.Circle, UIKit.Fire, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f));
            Pin(fireGlow.rectTransform, markers.Vec("fire"), new Vector2(0.45f, 0.35f));

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
            var wk = markers.Obj("wok");
            wokSpot = (o + wk.Vec("pos"), wk.Num("scale"));
            markers.Offset = o;

            var cam = markers.Obj("camera");
            var go = new GameObject("CookCamera");
            go.transform.SetParent(transform, false);
            setCam = go.AddComponent<Camera>();
            go.AddComponent<UnityEngine.Rendering.Universal.UniversalAdditionalCameraData>();
            go.transform.SetPositionAndRotation(o + cam.Vec("pos"), Quaternion.LookRotation(cam.Vec("forward"), cam.Vec("up")));
            setCam.usePhysicalProperties = true;
            setCam.focalLength = cam.Num("focal");
            setCam.sensorSize = new Vector2(cam.Num("sensor"), cam.Num("sensor") * 9f / 16f);
            setCam.gateFit = Camera.GateFitMode.Overscan;   // never crop the set on narrow or wide screens
            setCam.clearFlags = CameraClearFlags.SolidColor;
            setCam.backgroundColor = UIKit.Hex("#3b2a1c");
            setCam.nearClipPlane = 0.05f;
            setCam.farClipPlane = 30f;
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

        /// <summary>Shows exactly `id` at a spot, replacing whatever was there (null clears it).</summary>
        void ShowAt(ref GameObject current, ref string currentId, string id, Vector3 pos, float scale)
        {
            if (currentId == id) return;
            if (current) Destroy(current);
            current = id == null ? null : SpawnFood(id, pos, scale, 0);
            currentId = id;
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
            var ids = session.OpenRecipes().SelectMany(r => r.Ingredients.Keys).Distinct().Concat(SeasoningOrder);
            foreach (var id in ids)
            {
                if (!boardSpots.TryGetValue(id, out var spot)) continue;
                AddItem(art, id, Vector2.zero, Vector2.zero);
                Pin((RectTransform)items[items.Count - 1].cg.transform, spot.pos + new Vector3(0, 0.1f, 0), new Vector2(0.16f, 0.14f));
                SpawnFood(id, spot.pos, spot.scale, spot.rot);
            }
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
            Pin(Plaque(art, "灶台", 0, 0), markers.Vec("fire") + new Vector3(0, 0.46f, -0.02f), new Vector2(0.2f, 0.045f));
            // steam over the wok; the food in it is 3D
            var wok = UIKit.Rect(art, "WokInside", new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f));
            Pin(wok, wokSpot.pos + new Vector3(0, 0.06f, 0), new Vector2(0.33f, 0.1f));
            for (int i = 0; i < 5; i++)
                wokItems.Add(UIKit.Img(wok, "In" + i, null, Color.white, new Vector2(0.06f + i * 0.17f, 0.05f), new Vector2(0.3f + i * 0.17f, 0.75f), preserveAspect: true));
            wokFood = UIKit.Img(wok, "Food", null, Color.white, new Vector2(0.14f, -0.02f), new Vector2(0.86f, 0.95f), preserveAspect: true);
            for (int i = 0; i < 3; i++)
                steam.Add(UIKit.Img(wok, "Steam" + i, UIKit.Circle, new Color(1, 1, 1, 0), new Vector2(0.2f + i * 0.25f, 0.8f), new Vector2(0.4f + i * 0.25f, 1.3f), preserveAspect: true));
            stoveLabel = UIKit.Label(UIKit.Rect(wok, "Which", new Vector2(0.6f, -0.6f), new Vector2(1.2f, -0.1f)), "", 18, Color.white, TextAnchor.MiddleRight);

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

            // 出锅 sticks to the screen corner so a wide phone never crops it
            var btn = UIKit.Rect(root, "CookButton", new Vector2(0.79f, 0.03f), new Vector2(0.975f, 0.135f));
            var b = UIKit.Button(btn, "出锅", 52, Green, Color.white, TapCook);
            cookButton = (Image)b.targetGraphic;
            cookButtonText = btn.GetComponentInChildren<Text>();
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

        void Select(Recipe r)
        {
            if (selected != r) prep.Clear();
            selected = r;
            headerDish.sprite = DishSprite(r.Id);
            headerName.text = r.Name + " ▾";
        }

        IEnumerable<string> Needs(Recipe r) => r.Ingredients.Keys.Concat(r.Seasonings.Keys);

        void TapItem(string id)
        {
            var st = ActiveStove.State(GameSession.NowMs);
            if (selected == null) { ShowPicker(true); return; }
            if (st != StoveState.Idle) { Toast("锅里还有菜，先出锅", UIKit.Ink); return; }
            if (!Needs(selected).Contains(id)) { Toast($"{selected.Name}不用{session.Data.IngredientName(id)}", UIKit.Ink); return; }
            prep.Add(id);
            if (Needs(selected).All(prep.Contains))
            {
                var res = ActiveStove.Start(selected, GameSession.NowMs);
                if (res == Stove.StartResult.TierTooLow) Toast($"{selected.Name}要{CookRules.Name(selected.StoveTier)}", UIKit.Ink);
                prep.Clear();
            }
        }

        void TapCook()
        {
            var s = ActiveStove;
            var st = s.State(GameSession.NowMs);
            if (st == StoveState.Idle || st == StoveState.Locked)
            {
                Toast(selected == null ? "先选一道菜" : "先把亮起来的食材和调味放进锅里", UIKit.Ink);
                return;
            }
            if (session.FreeTray() < 0) { Toast("放置区满了，先把菜端出去", UIKit.Ink); return; }
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

        public void DemoTakeOut() => TapCook();

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

            // board: what the chosen dish needs lights up, what's in the wok is ticked
            var s = ActiveStove;
            var st = s.State(now);
            var needs = selected != null && st == StoveState.Idle ? Needs(selected).ToHashSet() : new HashSet<string>();
            foreach (var (id, img, ring, check, cg) in items)
            {
                img.enabled = false;   // the 3D food on the board is the picture
                bool need = needs.Contains(id), done = prep.Contains(id);
                ring.enabled = need && !done;
                ring.transform.localScale = Vector3.one * (1f + 0.04f * Mathf.Sin(t * 5f));
                check.enabled = done;
                cg.alpha = need ? (done ? 0.55f : 1f) : 0.55f;
            }

            // trays: the 3D dish on each (burnt dishes stay as they were, darkened by the UI badge)
            for (int i = 0; i < trays.Count; i++)
                ShowAt(ref trayModels[i], ref trayModelIds[i], session.Trays[i]?.dish.Id, traySpots[i].pos, traySpots[i].scale * 0.85f);
            for (int i = 0; i < trays.Count; i++)
            {
                var (dish, label, badge, badgeText) = trays[i];
                var tray = session.Trays[i];
                dish.enabled = tray != null;
                badge.enabled = badgeText.enabled = tray != null;
                label.transform.parent.gameObject.SetActive(tray != null);
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

            // wok, fire, steam
            int unlocked = session.Stoves.Count(x => x.Unlocked);
            stoveLabel.text = unlocked > 1 ? $"{CookRules.Name(s.Tier)}  {stoveIndex + 1}/{unlocked}" : "";
            bool cooking = st is StoveState.Cooking or StoveState.Burning;
            // the wok shows what is being put in; once it cooks, the dish itself (its 锅中 render, no bowl),
            // tossed about, browning and finally blackening when it burns
            var contents = st == StoveState.Idle ? prep.ToList() : new List<string>();
            for (int i = 0; i < wokItems.Count; i++)
            {
                var id = contents.ElementAtOrDefault(i);
                wokItems[i].enabled = id != null;
                if (id != null) wokItems[i].sprite = DishSprite(id) ?? UIKit.Circle;
            }
            foreach (var w in wokItems) w.enabled = false;
            // 3D: what is being put in, then the dish tossing in the wok
            var key = st == StoveState.Idle ? string.Join(",", contents) : "";
            if (key != prepKey)
            {
                foreach (var m in prepModels) Destroy(m);
                prepModels.Clear();
                for (int k = 0; k < contents.Count; k++)
                {
                    var off = new Vector3((k - (contents.Count - 1) / 2f) * 0.13f, 0.02f, (k % 2) * 0.06f);
                    var m = SpawnFood(contents[k], wokSpot.pos + off, 0.9f, k);
                    if (m) prepModels.Add(m);
                }
                prepKey = key;
            }
            ShowAt(ref wokModel, ref wokModelId, cooking ? s.Dish.Id + "_wok" : null, wokSpot.pos, wokSpot.scale);
            if (wokModel)
                wokModel.transform.position = wokSpot.pos + new Vector3(0, Mathf.Abs(Mathf.Sin(t * 6f)) * 0.03f, 0);
            wokFood.enabled = false;
            if (cooking)
            {
                wokFood.sprite = DishSprite(s.Dish.Id + "_wok") ?? DishSprite(s.Dish.Id);
                float p = Mathf.Clamp01((now - s.StartMs) / (float)(s.BurnAtMs - s.StartMs));
                wokFood.color = st == StoveState.Burning ? new Color(0.3f, 0.25f, 0.22f)
                    : Color.Lerp(new Color(1f, 1f, 1f), new Color(0.93f, 0.85f, 0.72f), p);
                wokFood.rectTransform.anchoredPosition = new Vector2(Mathf.Sin(t * 5f) * 4f, Mathf.Abs(Mathf.Sin(t * 6f)) * 6f);
            }
            fireGlow.color = new Color(1f, 0.62f, 0.2f, cooking ? 0.14f + 0.06f * Mathf.Sin(t * 9f) : 0f);
            fireGlow.transform.localScale = Vector3.one * (cooking ? 1.1f + 0.08f * Mathf.Sin(t * 13f) : 1f);
            for (int i = 0; i < steam.Count; i++)
            {
                float ph = (t * 0.6f + i / 3f) % 1f;
                float a = !cooking ? 0 : st == StoveState.Burning ? 0.55f : 0.35f;
                steam[i].color = st == StoveState.Burning ? new Color(0.35f, 0.33f, 0.32f, a * (1 - ph)) : new Color(1, 1, 1, a * (1 - ph));
                steam[i].rectTransform.anchoredPosition = new Vector2(Mathf.Sin(t * 2 + i) * 6f, ph * 70f);
            }

            UpdateGauge(s, st, now);
            resultText.enabled = t < resultUntil;

            cookButton.color = cooking ? Green : UIKit.Locked;
            cookButtonText.text = "出锅";
        }

        void UpdateGauge(Stove s, StoveState st, long now)
        {
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
