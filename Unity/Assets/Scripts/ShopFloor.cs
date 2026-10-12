using System.Collections;
using System.Collections.Generic;
using System.Linq;
using BianHe.Core;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.UI;

namespace BianHe
{
    /// <summary>
    /// The shop's furniture as bought (Premises; 《玩法与数值》04 桌椅与扩建). Tables not bought yet are put away. The next
    /// one for sale stands where it will go as a see-through sketch with its price over it, and a tap there opens the
    /// 添置 page. The 二楼 with the 雅间 (the model's Upstairs and Yajian groups, and the stair and walkway up to them) waits
    /// the same way until it is paid for. Then it goes up before the player's eyes, and a sign over it says it opens
    /// tomorrow. A bought table pops into place.
    /// </summary>
    public class ShopFloor : MonoBehaviour
    {
        enum Look { Hidden, Sketch, Real }

        /// <summary>A renderer showing as a sketch, and what it had on before.</summary>
        class Sketched
        {
            public Material[] Materials;
            public ShadowCastingMode Shadows;
        }

        Camera cam;
        readonly Dictionary<int, List<Transform>> tableParts = new();   // table number → the table and its stools
        readonly List<Transform> groups = new();                          // Upstairs, Yajian
        readonly List<Transform> expansion = new();                       // the 二楼's own parts (not its tables), the stair up
        readonly Dictionary<Renderer, Sketched> sketched = new();
        Material sketchMat;
        Offer shown;                                                      // what the sketch shows (null: none)
        Tag priceTag, openSign;

        /// <summary>A floating label over the shop, a world-space card that faces the camera and bobs.</summary>
        class Tag
        {
            public RectTransform Rt;
            public Text Text;
            public Image Bg, Tail;
            public Vector3 At;
            public bool Bob;
        }

        /// <summary>Something is popping in or going up.</summary>
        public bool Busy { get; private set; }

        /// <summary>The shop has an upper floor to build (三级 on).</summary>
        public bool HasUpstairs => groups.Count > 0;

        void Awake()
        {
            var shader = Resources.Load<Shader>("Shaders/Ghost");
            if (shader) sketchMat = new Material(shader) { name = "M_Sketch" };
            else Debug.LogError("ShopFloor: Resources/Shaders/Ghost not found");
        }

        /// <summary>Takes up a shop: its tables (D_Table_&lt;n&gt; and their stools), and its 二楼 if it has one.</summary>
        public void Setup(Transform shop, Camera camera)
        {
            RestoreAll();
            DestroyTag(priceTag);
            DestroyTag(openSign);
            priceTag = openSign = null;
            shown = null;
            cam = camera;
            tableParts.Clear();
            groups.Clear();
            expansion.Clear();

            var all = shop.GetComponentsInChildren<Transform>(true);
            Transform Named(string n) => all.FirstOrDefault(x => x.name == n);
            for (int n = 1; ; n++)
            {
                var table = Named($"D_Table_{n}");
                if (!table) break;
                var parts = new List<Transform> { table };
                for (int k = 1; k <= 4; k++)
                {
                    var stool = Named($"D_Stool_{n}_{k}") ?? (n == 1 ? Named($"D_Stool_{k}") : null);   // 初始·1桌: D_Stool_1…4
                    if (stool) parts.Add(stool);
                }
                tableParts[n] = parts;
            }
            var furniture = new HashSet<Transform>(tableParts.Values.SelectMany(p => p));
            foreach (var g in new[] { "Upstairs", "Yajian" }.Select(Named).Where(g => g))
            {
                groups.Add(g);
                foreach (Transform c in g)
                    if (!furniture.Contains(c)) expansion.Add(c);
            }
            if (HasUpstairs)   // the stair (and the walkway to it) leads up there: built with it
                expansion.AddRange(new[] { "D_Stairs", "D_Walkway" }.Select(Named).Where(t => t));
        }

        /// <summary>
        /// Shows the shop as bought: the tables bought, and the 二楼 once paid for, stand as they are; the next thing for
        /// sale, if the stage allows it, as a sketch with its price; everything else is put away. While the 二楼 is built but
        /// not open yet (it opens the day after it was paid for), a sign over it says so.
        /// </summary>
        public void Show(Premises premises, Offer next, int day)
        {
            var sale = next is { Allowed: true } ? next : null;
            var up = premises.Expanded ? Look.Real : sale?.Kind == OfferKind.Expansion ? Look.Sketch : Look.Hidden;
            foreach (var g in groups) g.gameObject.SetActive(up != Look.Hidden);
            foreach (var t in expansion) Set(t, up);
            foreach (var kv in tableParts)
            {
                int n = kv.Key;
                var look = premises.Bought.Contains(n) ? Look.Real : sale != null && sale.Tables.Contains(n) ? Look.Sketch : Look.Hidden;
                foreach (var t in kv.Value) Set(t, look);
            }

            shown = sale;
            if (sale != null)
            {
                var b = BoundsOf(SaleParts(sale));
                priceTag ??= MakeTag("PriceTag");
                priceTag.At = new Vector3(b.center.x, b.max.y + (sale.Kind == OfferKind.Expansion ? 0.5f : 0.75f), b.center.z);
                SetText(priceTag, sale.Kind == OfferKind.Expansion ? $"扩建二楼·{sale.Price / 100} 文" : $"添桌·{sale.Price / 100} 文");
                priceTag.Bob = true;
            }
            if (priceTag != null) priceTag.Rt.gameObject.SetActive(sale != null);

            bool soon = premises.Expanded && !premises.ExpansionOpen(day) && HasUpstairs;
            if (soon)
            {
                var b = BoundsOf(expansion.Concat(premises.Bought.Where(premises.IsExpansionTable).SelectMany(PartsOf)));
                openSign ??= MakeTag("OpenSign");
                openSign.At = new Vector3(b.center.x, b.max.y + 0.6f, b.center.z);
                SetText(openSign, "二楼明天开张");
                openSign.Bg.color = openSign.Tail.color = UIKit.Good;
                openSign.Text.color = Color.white;
            }
            if (openSign != null) openSign.Rt.gameObject.SetActive(soon);
        }

        /// <summary>The price tag's colour: the curtains' blue when it can be paid for now, paper when the money isn't there yet.</summary>
        public void SetAffordable(bool yes)
        {
            if (priceTag == null) return;
            priceTag.Bg.color = priceTag.Tail.color = yes ? UIKit.Accent : UIKit.Paper;
            priceTag.Text.color = yes ? Color.white : UIKit.InkSoft;
        }

        /// <summary>A tap on the sketch for sale or on its price tag.</summary>
        public bool HitSale(Vector2 screen)
        {
            if (shown == null || Busy || priceTag == null || !priceTag.Rt.gameObject.activeInHierarchy) return false;
            var corners = new Vector3[4];
            priceTag.Rt.GetWorldCorners(corners);
            var s = corners.Select(c => (Vector2)cam.WorldToScreenPoint(c)).ToArray();
            var rect = Rect.MinMaxRect(s.Min(p => p.x), s.Min(p => p.y), s.Max(p => p.x), s.Max(p => p.y));
            if (rect.Contains(screen)) return true;
            var ray = cam.ScreenPointToRay(screen);
            return sketched.Keys.Any(r => r && r.gameObject.activeInHierarchy && r.bounds.IntersectRay(ray));
        }

        /// <summary>Everything that shows what is for sale: its tables (and the 二楼's own parts).</summary>
        IEnumerable<Transform> SaleParts(Offer o) =>
            (o.Kind == OfferKind.Expansion ? expansion : Enumerable.Empty<Transform>()).Concat(o.Tables.SelectMany(PartsOf));

        IEnumerable<Transform> PartsOf(int table) => tableParts.TryGetValue(table, out var p) ? p : Enumerable.Empty<Transform>();

        /// <summary>The middle of what the 二楼 will be (its own parts and the tables it brings), for the camera.</summary>
        public Bounds ExpansionBounds(IEnumerable<int> tables) => BoundsOf(expansion.Concat(tables.SelectMany(PartsOf)));

        public Bounds TableBounds(int table) => BoundsOf(PartsOf(table));

        void Set(Transform t, Look look)
        {
            t.gameObject.SetActive(look != Look.Hidden);
            foreach (var r in t.GetComponentsInChildren<Renderer>(true))
            {
                if (look == Look.Sketch && sketchMat)
                {
                    if (sketched.ContainsKey(r)) continue;
                    sketched[r] = new Sketched { Materials = r.sharedMaterials, Shadows = r.shadowCastingMode };
                    r.sharedMaterials = Enumerable.Repeat(sketchMat, r.sharedMaterials.Length).ToArray();
                    r.shadowCastingMode = ShadowCastingMode.Off;
                }
                else if (sketched.TryGetValue(r, out var was))
                {
                    r.sharedMaterials = was.Materials;
                    r.shadowCastingMode = was.Shadows;
                    sketched.Remove(r);
                }
            }
        }

        void RestoreAll()
        {
            foreach (var kv in sketched)
                if (kv.Key)
                {
                    kv.Key.sharedMaterials = kv.Value.Materials;
                    kv.Key.shadowCastingMode = kv.Value.Shadows;
                }
            sketched.Clear();
        }

        static Bounds BoundsOf(IEnumerable<Transform> parts)
        {
            Bounds b = default;
            bool any = false;
            foreach (var t in parts)
                foreach (var r in t.GetComponentsInChildren<Renderer>())
                {
                    if (!any) { b = r.bounds; any = true; }
                    else b.Encapsulate(r.bounds);
                }
            return b;
        }

        // ------------------------------------------------------------------ popping in and building

        /// <summary>A bought table (with its stools) pops into place: the table first, then the stools one after another.</summary>
        public IEnumerator PopIn(int table)
        {
            Busy = true;
            var parts = PartsOf(table).Where(t => t.gameObject.activeInHierarchy).ToList();
            var growing = parts.Select(t => new Growing(t, Grow.Pop)).ToList();   // all at nothing before the next frame
            for (int i = 0; i < growing.Count; i++)
                StartCoroutine(growing[i].Run(this, i == 0 ? 0f : 0.12f + 0.06f * i, 0.42f));
            while (growing.Any(g => !g.Done)) yield return null;
            Busy = false;
        }

        /// <summary>
        /// The 二楼 goes up: the storey under it and the stair first, then the floor, the walls, railings and screens,
        /// each rising from its foot (a floor, thin, spreading out from its middle instead) with a puff of dust, and last
        /// the tables it brings, popping in.
        /// </summary>
        public IEnumerator Build(IEnumerable<int> tables)
        {
            Busy = true;
            foreach (var g in groups) g.gameObject.SetActive(true);
            foreach (var t in expansion) Set(t, Look.Real);
            var furniture = tables.SelectMany(PartsOf).ToList();
            foreach (var t in furniture) Set(t, Look.Real);
            if (priceTag != null) priceTag.Rt.gameObject.SetActive(false);
            shown = null;
            // low before high, and on one level the big pieces first
            var structure = expansion.Where(t => t.gameObject.activeInHierarchy)
                .Select(t => (t, b: BoundsOf(new[] { t })))
                .OrderBy(x => Mathf.Round(x.b.min.y / 0.5f)).ThenByDescending(x => x.b.size.x * x.b.size.y * x.b.size.z)
                .Select(x => x.t).ToList();
            var rising = structure.Select(t => new Growing(t, BoundsOf(new[] { t }).size.y < 0.5f ? Grow.Spread : Grow.Rise)).ToList();
            var popping = furniture.Where(t => t.gameObject.activeInHierarchy).Select(t => new Growing(t, Grow.Pop)).ToList();
            float at = 0f;
            foreach (var g in rising)
            {
                StartCoroutine(g.Run(this, at, 0.55f));
                at += Mathf.Clamp(1.8f / Mathf.Max(1, rising.Count), 0.14f, 0.3f);
            }
            at += 0.35f;
            for (int i = 0; i < popping.Count; i++)
                StartCoroutine(popping[i].Run(this, at + (i % 5 == 0 ? 0.12f * (i / 5) : 0.12f * (i / 5) + 0.05f * (i % 5)), 0.4f));
            while (rising.Any(g => !g.Done) || popping.Any(g => !g.Done)) yield return null;
            Busy = false;
        }

        /// <summary>How a part grows into place: up from flat (a wall), out from its middle (a floor, which rising would
        /// press its rugs into its boards), or from nothing, a little past its size and back (a table).</summary>
        enum Grow { Rise, Spread, Pop }

        /// <summary>
        /// One part growing into place about the middle of its foot. It is held at its start from the moment this is made,
        /// so nothing shows whole for a frame; at the end it has its own transform back exactly.
        /// </summary>
        class Growing
        {
            readonly Transform part, parent, pivot;
            readonly Vector3 localPos, localScale;
            readonly Quaternion localRot;
            readonly int sibling;
            readonly Grow how;
            readonly Bounds foot;
            public bool Done;

            public Growing(Transform t, Grow how)
            {
                part = t;
                this.how = how;
                parent = t.parent;
                localPos = t.localPosition;
                localRot = t.localRotation;
                localScale = t.localScale;
                sibling = t.GetSiblingIndex();
                var b = BoundsOf(new[] { t });
                foot = b;
                pivot = new GameObject("Grow_" + t.name).transform;
                pivot.position = new Vector3(b.center.x, b.min.y, b.center.z);
                t.SetParent(pivot, true);
                pivot.localScale = Scale(0f);
            }

            Vector3 Scale(float s)
            {
                s = Mathf.Max(0.001f, s);
                return how switch { Grow.Rise => new Vector3(1f, s, 1f), Grow.Spread => new Vector3(s, 1f, s), _ => Vector3.one * s };
            }

            public IEnumerator Run(ShopFloor floor, float delay, float seconds)
            {
                if (delay > 0) yield return new WaitForSeconds(delay);
                floor.Puff(foot);
                for (float t = 0; t < seconds; t += Time.deltaTime)
                {
                    float k = t / seconds;
                    // rising and spreading: eased out; popping: past its size by a tenth, then back
                    pivot.localScale = Scale(how == Grow.Pop ? 1f + 2.70158f * Mathf.Pow(k - 1f, 3f) + 1.70158f * Mathf.Pow(k - 1f, 2f)
                                                             : 1f - Mathf.Pow(1f - k, 3f));
                    yield return null;
                }
                part.SetParent(parent, true);
                part.SetSiblingIndex(sibling);
                part.localPosition = localPos;
                part.localRotation = localRot;
                part.localScale = localScale;
                Object.Destroy(pivot.gameObject);
                Done = true;
            }
        }

        /// <summary>
        /// A puff of dust along the foot of something going up: soft sandy rounds round the edge of its footprint, a few
        /// more the longer that is, drifting outward and up as they fade.
        /// </summary>
        void Puff(Bounds b)
        {
            float w = Mathf.Max(0.2f, b.size.x * 0.9f), d = Mathf.Max(0.2f, b.size.z * 0.9f);
            int n = Mathf.Clamp(Mathf.RoundToInt((w + d) * 2f / 0.9f), 4, 14);
            float radius = Mathf.Clamp(0.08f * Mathf.Sqrt(w + d), 0.07f, 0.2f);
            for (int i = 0; i < n; i++)
            {
                // a point along the footprint's edge, and out from its middle
                float u = (i + Random.value * 0.6f) / n * 2f * (w + d), x, z;
                if (u < w) { x = u - w / 2; z = -d / 2; }
                else if (u < w + d) { x = w / 2; z = u - w - d / 2; }
                else if (u < 2 * w + d) { x = 2 * w + d - u - w / 2; z = d / 2; }
                else { x = -w / 2; z = 2 * w + 2 * d - u - d / 2; }
                var at = new Vector3(b.center.x + x, b.min.y + 0.04f, b.center.z + z);
                var outward = new Vector3(x, 0, z).normalized;
                var go = new GameObject("Dust", typeof(SpriteRenderer));
                go.transform.SetParent(transform, false);
                var sr = go.GetComponent<SpriteRenderer>();
                sr.sprite = SoftRound;
                sr.sortingOrder = 5;
                StartCoroutine(Drift(go.transform, sr, at, outward * radius * 1.6f, radius * (0.8f + Random.value * 0.5f)));
            }
        }

        IEnumerator Drift(Transform t, SpriteRenderer sr, Vector3 from, Vector3 by, float radius)
        {
            var c = UIKit.Hex("#d9c7a3");   // sand, a shade darker than the paper behind the shop
            const float seconds = 0.7f;
            for (float k = 0; k < 1f; k += Time.deltaTime / seconds)
            {
                float e = 1f - (1f - k) * (1f - k);
                t.position = from + by * e + Vector3.up * (radius * 1.2f * e);
                t.rotation = cam ? cam.transform.rotation : Quaternion.identity;
                t.localScale = Vector3.one * (radius * 2f * (0.7f + 0.6f * e));   // the sprite is 1 m across
                sr.color = new Color(c.r, c.g, c.b, 0.72f * (1f - k) * Mathf.Clamp01(k * 8f));
                yield return null;
            }
            Destroy(t.gameObject);
        }

        static Sprite softRound;

        /// <summary>A white round, 1 m across, solid in the middle and fading out over its outer half: a wisp of dust.</summary>
        static Sprite SoftRound
        {
            get
            {
                if (softRound) return softRound;
                const int n = 64;
                var tex = new Texture2D(n, n, TextureFormat.RGBA32, false) { wrapMode = TextureWrapMode.Clamp };
                var px = new Color[n * n];
                for (int y = 0; y < n; y++)
                    for (int x = 0; x < n; x++)
                    {
                        float r = new Vector2(x + 0.5f - n / 2f, y + 0.5f - n / 2f).magnitude / (n / 2f);
                        float a = Mathf.Clamp01((1f - r) / 0.5f);
                        px[y * n + x] = new Color(1f, 1f, 1f, a * a * (3f - 2f * a));
                    }
                tex.SetPixels(px);
                tex.Apply();
                return softRound = Sprite.Create(tex, new Rect(0, 0, n, n), new Vector2(0.5f, 0.5f), n);
            }
        }

        // ------------------------------------------------------------------ tags

        Tag MakeTag(string name)
        {
            var go = new GameObject(name, typeof(Canvas));
            var canvas = go.GetComponent<Canvas>();
            canvas.renderMode = RenderMode.WorldSpace;
            canvas.worldCamera = cam;
            var tg = new Tag { Rt = (RectTransform)go.transform };
            tg.Rt.SetParent(transform, false);
            tg.Rt.sizeDelta = new Vector2(380, 104);
            var tail = UIKit.Rect(tg.Rt, "Tail", new Vector2(0.5f, 0), new Vector2(0.5f, 0));
            tail.sizeDelta = new Vector2(28, 28);
            tail.anchoredPosition = new Vector2(0, -6);
            tail.localRotation = Quaternion.Euler(0, 0, 45);
            tg.Tail = tail.gameObject.AddComponent<Image>();
            var bg = UIKit.Rect(tg.Rt, "Bg", Vector2.zero, Vector2.one);
            tg.Bg = UIKit.Panel(bg, UIKit.Accent);
            tg.Tail.color = UIKit.Accent;
            tg.Text = UIKit.Label(bg, "", 52, Color.white, TextAnchor.MiddleCenter, FontStyle.Bold);
            return tg;
        }

        /// <summary>A tag's text, the card as wide as it needs.</summary>
        static void SetText(Tag tg, string text)
        {
            tg.Text.text = text;
            tg.Rt.sizeDelta = new Vector2(Mathf.Max(240f, tg.Text.preferredWidth + 64f), 108f);
        }

        static void DestroyTag(Tag tg)
        {
            if (tg?.Rt) Destroy(tg.Rt.gameObject);
        }

        void LateUpdate()
        {
            if (!cam) return;
            float s = 0.0042f * Mathf.Clamp(cam.orthographicSize / 4f, 0.6f, 1.6f);   // about the same size on screen, as the 案台's tag
            foreach (var tg in new[] { priceTag, openSign })
            {
                if (tg == null || !tg.Rt.gameObject.activeSelf) continue;
                tg.Rt.rotation = cam.transform.rotation;
                tg.Rt.localScale = Vector3.one * s;
                tg.Rt.position = tg.At + Vector3.up * (tg.Bob ? Mathf.Sin(Time.time * 2.4f) * 0.06f : 0f);
            }
        }
    }
}
