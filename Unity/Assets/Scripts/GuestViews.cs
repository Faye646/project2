using System.Collections.Generic;
using System.Linq;
using BianHe.Core;
using UnityEngine;
using UnityEngine.UI;

namespace BianHe
{
    /// <summary>
    /// Stand-in 纸片人 for the guests until the real cut-outs are drawn: flat cards that always face the
    /// camera, seated on the stools of their table or queueing by the steps, plus a bubble over each table
    /// with its state (等菜 with the patience left, 催单, 用餐, the bill) and one by the door for those waiting.
    /// The tables are the shop's D_Table_&lt;n&gt; with their stools D_Stool_&lt;n&gt;_&lt;k&gt; (初始·1桌: D_Stool_1…4).
    /// </summary>
    public class GuestViews : MonoBehaviour
    {
        /// <summary>A bubble over a table (or the door): a world-space card that faces the camera.</summary>
        class Bubble
        {
            public RectTransform Rt;
            public Text Text;
            public Image Bg, Bar;
            public string Flash;
            public float FlashUntil;
        }

        /// <summary>One dining table: its top, the stools round it, what stands on it already (the cups), the dishes
        /// served on it and the seat of whoever ordered each, and its bubble.</summary>
        class TableSpot
        {
            public Transform Table;
            public readonly List<Transform> Stools = new();
            public readonly List<Vector3> Seats = new();
            public Vector3 Top;
            public Rect Rect;                                           // the top, seen from above (x, z)
            public readonly List<(Vector2 c, float r)> Things = new();  // what stands on it already (the cups)
            public readonly Dictionary<Plate, GameObject> Served = new();
            public readonly Dictionary<Plate, Vector3> ServedSeat = new();
            public Bubble Bubble;
        }

        Camera cam;
        readonly List<TableSpot> tables = new();
        readonly List<Vector3> doorSpots = new();
        readonly Dictionary<Guest, (SpriteRenderer clothes, SpriteRenderer lines)> dolls = new();
        Bubble doorBubble;

        static (Sprite clothes, Sprite lines) sitting, standing;
        static readonly Color[] Clothes = { UIKit.Hex("#5d7fa6"), UIKit.Hex("#9b6a45"), UIKit.Hex("#7d8f6a"), UIKit.Hex("#c49a52"), UIKit.Hex("#8a5f7a") };

        /// <summary>How many tables the shop's model has.</summary>
        public int TableCount => tables.Count;

        /// <summary>Takes up a shop (its tables, stools and queue spots); whatever showed the last one goes.</summary>
        public void Setup(Transform level, Camera camera)
        {
            cam = camera;
            Clear();
            var all = level.GetComponentsInChildren<Transform>(true);
            Transform Named(string n) => all.FirstOrDefault(x => x.name == n);
            Vector3 Top(Transform t)
            {
                var b = new Bounds(t.position, Vector3.zero);
                foreach (var r in t.GetComponentsInChildren<Renderer>()) b.Encapsulate(r.bounds);
                return new Vector3(b.center.x, b.max.y, b.center.z);
            }
            for (int n = 1; ; n++)
            {
                var table = Named($"D_Table_{n}");
                if (!table) break;
                var spot = new TableSpot { Table = table };
                for (int k = 1; k <= 4; k++)
                {
                    var stool = Named($"D_Stool_{n}_{k}") ?? (n == 1 ? Named($"D_Stool_{k}") : null);
                    if (!stool) continue;
                    spot.Stools.Add(stool);
                    spot.Seats.Add(Top(stool));
                }
                spot.Top = Top(table);
                MeasureTable(spot);
                spot.Bubble = MakeBubble($"TableBubble_{n}", spot.Top + Vector3.up * 1.35f);
                tables.Add(spot);
            }
            // queue spots are empties in the white model (Spot_Queue_1…4, on the stepping stones)
            foreach (var t in all.Where(x => x.name.StartsWith("Spot_Queue_")).OrderBy(x => x.name))
                doorSpots.Add(t.position);
            if (doorSpots.Count == 0)
                doorSpots.Add(tables.Count > 0 ? tables[0].Top + new Vector3(0, -tables[0].Top.y, -3f) : Vector3.zero);
            doorBubble = MakeBubble("DoorBubble", doorSpots[0] + Vector3.up * 2.1f);
        }

        void Clear()
        {
            foreach (var d in dolls.Values)
                if (d.clothes) Destroy(d.clothes.transform.parent.gameObject);
            dolls.Clear();
            foreach (var t in tables)
            {
                foreach (var go in t.Served.Values)
                    if (go) Destroy(go);
                if (t.Bubble?.Rt) Destroy(t.Bubble.Rt.gameObject);
            }
            tables.Clear();
            doorSpots.Clear();
            if (doorBubble?.Rt) Destroy(doorBubble.Rt.gameObject);
            doorBubble = null;
        }

        /// <summary>
        /// A table's top, from its mesh (the level models are imported readable): the top board's surface is as high as
        /// the vertices along its edge go, where dishes stand; whatever stands higher on it (the cups) is gathered into
        /// round things kept clear of. Without the vertices: 6 cm under the top of its box, as the cups stand.
        /// </summary>
        static void MeasureTable(TableSpot spot)
        {
            var table = spot.Table;
            var b = new Bounds(table.position, Vector3.zero);
            foreach (var r in table.GetComponentsInChildren<Renderer>()) b.Encapsulate(r.bounds);
            spot.Rect = Rect.MinMaxRect(b.min.x + 0.03f, b.min.z + 0.03f, b.max.x - 0.03f, b.max.z - 0.03f);
            spot.Top = new Vector3(b.center.x, b.max.y - 0.06f, b.center.z);
            var pts = new List<Vector3>();
            foreach (var mf in table.GetComponentsInChildren<MeshFilter>())
            {
                if (mf.sharedMesh == null || !mf.sharedMesh.isReadable) continue;
                var m = mf.transform.localToWorldMatrix;
                foreach (var v in mf.sharedMesh.vertices) pts.Add(m.MultiplyPoint3x4(v));
            }
            if (pts.Count == 0) return;
            float edge = Mathf.Min(b.extents.x, b.extents.z) * 0.85f;   // the outer band of the top: no cups there
            float surface = pts.Where(q => Mathf.Max(Mathf.Abs(q.x - b.center.x), Mathf.Abs(q.z - b.center.z)) > edge)
                               .Select(q => q.y).DefaultIfEmpty(b.max.y - 0.06f).Max();
            spot.Top = new Vector3(b.center.x, surface, b.center.z);
            // what stands on it, in 6 cm cells joined into things
            var cells = new Dictionary<Vector2Int, List<Vector3>>();
            foreach (var q in pts.Where(q => q.y > surface + 0.01f))
            {
                var key = new Vector2Int(Mathf.FloorToInt(q.x / 0.06f), Mathf.FloorToInt(q.z / 0.06f));
                if (!cells.TryGetValue(key, out var l)) cells[key] = l = new List<Vector3>();
                l.Add(q);
            }
            var left = new HashSet<Vector2Int>(cells.Keys);
            while (left.Count > 0)
            {
                var start = left.First();
                var group = new List<Vector3>();
                var todo = new Stack<Vector2Int>();
                todo.Push(start);
                left.Remove(start);
                while (todo.Count > 0)
                {
                    var k = todo.Pop();
                    group.AddRange(cells[k]);
                    for (int dx = -1; dx <= 1; dx++)
                        for (int dz = -1; dz <= 1; dz++)
                        {
                            var n = new Vector2Int(k.x + dx, k.y + dz);
                            if (left.Remove(n)) todo.Push(n);
                        }
                }
                var c = new Vector2(group.Average(q => q.x), group.Average(q => q.z));
                float rad = group.Max(q => (new Vector2(q.x, q.z) - c).magnitude);
                spot.Things.Add((c, rad));
            }
        }

        /// <summary>The bill flashed over the table that paid.</summary>
        public void Flash(int table, string msg)
        {
            if (table < 0 || table >= tables.Count) return;
            tables[table].Bubble.Flash = msg;
            tables[table].Bubble.FlashUntil = Time.time + 2.5f;
        }

        public void Sync(Service service, long now)
        {
            var live = new HashSet<Guest>();
            var atTable = new Party[tables.Count];
            var atDoor = new List<Party>();
            foreach (var p in service.Parties)
            {
                if (p.State is PartyState.Waiting or PartyState.Dining && p.Table >= 0 && p.Table < tables.Count) atTable[p.Table] = p;
                else if (p.State == PartyState.AtDoor) atDoor.Add(p);
            }
            for (int t = 0; t < tables.Count; t++)
            {
                var p = atTable[t];
                if (p == null) continue;
                var seats = tables[t].Seats;
                for (int i = 0; i < p.Guests.Count; i++)
                {
                    live.Add(p.Guests[i]);
                    Doll(p.Guests[i], true).clothes.transform.parent.position = seats.Count > 0 ? seats[i % seats.Count] : tables[t].Top;
                }
            }
            // those waiting for a table queue along the queue spots, a step to the side once those are taken
            int q = 0;
            foreach (var p in atDoor)
                foreach (var g in p.Guests)
                {
                    live.Add(g);
                    var at = doorSpots[q % doorSpots.Count] + cam.transform.right * (0.5f * (q / doorSpots.Count));
                    Doll(g, false).clothes.transform.parent.position = at;
                    q++;
                }
            foreach (var g in dolls.Keys.Where(g => !live.Contains(g)).ToList())
            {
                Destroy(dolls[g].clothes.transform.parent.gameObject);
                dolls.Remove(g);
            }

            for (int t = 0; t < tables.Count; t++)
            {
                SyncDishes(tables[t], atTable[t]);
                SyncTableBubble(tables[t].Bubble, atTable[t], now);
            }
            int waiting = atDoor.Sum(p => p.Guests.Count);
            ShowBubble(doorBubble, waiting > 0 ? $"门口 {waiting} 位在等" : null, UIKit.Paper, UIKit.Ink, -1);
        }

        /// <summary>The dishes served to the party at a table, in front of whoever ordered each, laid out afresh
        /// whenever one comes or goes.</summary>
        void SyncDishes(TableSpot spot, Party party)
        {
            var livePlates = new HashSet<Plate>();
            bool changed = false;
            if (party != null)
                for (int i = 0; i < party.Guests.Count; i++)
                    foreach (var pl in party.Guests[i].Plates)
                    {
                        if (!pl.Served) continue;
                        livePlates.Add(pl);
                        if (spot.Served.ContainsKey(pl)) continue;
                        spot.Served[pl] = PlaceDish(pl, spot);
                        spot.ServedSeat[pl] = spot.Seats.Count > 0 ? spot.Seats[i % spot.Seats.Count] : spot.Top;
                        changed = true;
                    }
            foreach (var pl in spot.Served.Keys.Where(pl => !livePlates.Contains(pl)).ToList())
            {
                if (spot.Served[pl]) Destroy(spot.Served[pl]);
                spot.Served.Remove(pl);
                spot.ServedSeat.Remove(pl);
                changed = true;
            }
            if (changed) LayOutTable(spot);
        }

        void SyncTableBubble(Bubble b, Party party, long now)
        {
            if (Time.time < b.FlashUntil) { ShowBubble(b, b.Flash, UIKit.Good, Color.white, -1); return; }
            if (party == null) { ShowBubble(b, null, UIKit.Paper, UIKit.Ink, -1); return; }
            if (party.State == PartyState.Dining) { ShowBubble(b, "用餐中", UIKit.Paper, UIKit.Ink, -1); return; }
            long left = party.OrderedMs + party.PatienceMs - now;
            int todo = party.Plates.Count(pl => !pl.Served);
            if (!party.Late)
                ShowBubble(b, $"等菜 {todo} 份·{CookRules.Seconds(left)}秒", UIKit.Paper, UIKit.Ink, Mathf.Clamp01(left / (float)party.PatienceMs));
            else
                ShowBubble(b, $"催单！{CookRules.Seconds(party.LeaveAtMs - now)}秒", UIKit.Hex("#c0462c"), Color.white,
                           Mathf.Clamp01((party.LeaveAtMs - now) / (float)ServiceRules.LeaveAfterLateMs));
        }

        static void ShowBubble(Bubble b, string text, Color bg, Color fg, float bar)
        {
            if (b == null) return;
            b.Rt.gameObject.SetActive(text != null);
            if (text == null) return;
            b.Text.text = text;
            b.Text.color = fg;
            b.Bg.color = bg;
            b.Bar.transform.parent.gameObject.SetActive(bar >= 0);
            b.Bar.fillAmount = Mathf.Max(0, bar);
            b.Bar.color = bar > 0.35f ? UIKit.Good : UIKit.Fire;
        }

        void LateUpdate()
        {
            if (!cam) return;
            var flat = Quaternion.Euler(90f, cam.transform.eulerAngles.y, 0f);
            foreach (var d in dolls.Values)
            {
                var root = d.clothes.transform.parent;
                root.rotation = cam.transform.rotation;
                // its shadow stays flat on what it stands or sits on, the long way across the view
                var shadow = root.Find("Shadow");
                if (shadow) shadow.SetPositionAndRotation(root.position + Vector3.up * 0.003f, flat);
            }
            // the bubbles face the camera and keep about the same size on screen, a little smaller when zoomed out
            // over a shop with many tables, so that neighbours' bubbles don't run into each other
            float k = 0.0042f * Mathf.Clamp(cam.orthographicSize / 4f, 0.6f, tables.Count > 2 ? 1.25f : 1.6f);
            foreach (var b in tables.Select(t => t.Bubble).Append(doorBubble))
            {
                if (b?.Rt == null || !b.Rt.gameObject.activeSelf) continue;
                b.Rt.rotation = cam.transform.rotation;
                b.Rt.localScale = Vector3.one * k;
            }
        }

        (SpriteRenderer clothes, SpriteRenderer lines) Doll(Guest g, bool sit)
        {
            if (!dolls.TryGetValue(g, out var d))
            {
                var go = new GameObject("Guest");
                go.transform.SetParent(transform, false);
                SpriteRenderer Layer(string n, int order)
                {
                    var c = new GameObject(n);
                    c.transform.SetParent(go.transform, false);
                    var sr = c.AddComponent<SpriteRenderer>();
                    sr.sortingOrder = order;
                    return sr;
                }
                d = (Layer("Clothes", 0), Layer("Lines", 1));
                d.clothes.color = Clothes[(g.GetHashCode() & 0x7fffffff) % Clothes.Length];
                var shadow = Layer("Shadow", -1);   // a cartoon's round shadow under the card figure
                shadow.sprite = BlobShadow;
                shadow.color = new Color(0.2f, 0.12f, 0.13f, 0.6f);   // a third darker, as the cast shadows
                dolls[g] = d;
            }
            d.clothes.transform.parent.Find("Shadow").localScale = sit ? new Vector3(0.36f, 0.24f, 1f) : new Vector3(0.44f, 0.28f, 1f);
            if (sit && sitting.clothes == null) sitting = MakeDoll(0.0f);
            if (!sit && standing.clothes == null) standing = MakeDoll(1.6f);
            var s = sit ? sitting : standing;
            d.clothes.sprite = s.clothes;
            d.lines.sprite = s.lines;
            return d;
        }

        static Sprite blob;

        /// <summary>A round shadow with a soft rim, 1 m across (each figure's is scaled to it), white for tinting.</summary>
        static Sprite BlobShadow
        {
            get
            {
                if (blob) return blob;
                const int n = 64;
                var tex = new Texture2D(n, n, TextureFormat.RGBA32, false) { wrapMode = TextureWrapMode.Clamp };
                var px = new Color[n * n];
                for (int y = 0; y < n; y++)
                    for (int x = 0; x < n; x++)
                    {
                        float r = new Vector2(x + 0.5f - n / 2f, y + 0.5f - n / 2f).magnitude / (n / 2f);
                        float e = Mathf.Clamp01((r - 0.8f) / 0.2f);   // the rim: the last fifth of the radius
                        px[y * n + x] = new Color(1f, 1f, 1f, 1f - e * e * (3f - 2f * e));
                    }
                tex.SetPixels(px);
                tex.Apply();
                return blob = Sprite.Create(tex, new Rect(0, 0, n, n), new Vector2(0.5f, 0.5f), n);
            }
        }

        /// <summary>
        /// A card figure in two layers: the clothes as a white mask (tinted per guest) and the head, hair
        /// and ink outline on top. `legs` adds standing height; seated guests are just the upper body.
        /// </summary>
        static (Sprite clothes, Sprite lines) MakeDoll(float legs)
        {
            int w = 64, h = Mathf.RoundToInt(96 + 64 * legs);
            var ink = UIKit.Hex("#4a3322");
            var skin = UIKit.Hex("#f1d3b3");
            var hairC = UIKit.Hex("#3b2a20");
            var cloth = new Color[w * h];
            var lines = new Color[w * h];
            float headR = 13, headY = h - 16, cx = w / 2f;
            float bodyTop = headY - headR + 2, bodyBottom = 3;
            for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++)
            {
                float dx = x + 0.5f - cx, y0 = y + 0.5f;
                float t = Mathf.InverseLerp(bodyTop, bodyBottom, y0);
                float half = Mathf.Lerp(14, 22, t);
                float down = bodyTop - y0;                                   // rounded shoulders
                if (down < 8) half *= Mathf.Sqrt(Mathf.Max(0, 1 - Mathf.Pow((8 - down) / 8f, 2))) * 0.45f + 0.55f;
                float edgeBody = Mathf.Min(half - Mathf.Abs(dx), Mathf.Min(y0 - bodyBottom, bodyTop - y0));
                float dh = Mathf.Sqrt(dx * dx + (y0 - headY) * (y0 - headY));
                float edgeHead = headR - dh;
                int i = y * w + x;
                if (edgeBody >= 0)
                {
                    cloth[i] = Color.white;
                    if (edgeBody < 2.5f) lines[i] = ink;
                    else if (Mathf.Abs(dx) < 1.2f && y0 > bodyBottom + 6) lines[i] = new Color(ink.r, ink.g, ink.b, 0.5f);   // robe seam
                }
                if (edgeHead >= 0)
                {
                    cloth[i] = Color.clear;
                    lines[i] = edgeHead < 2.5f ? ink : (y0 > headY + 2 && dh > 3.5f) ? hairC : skin;
                }
            }
            Sprite Make(Color[] px)
            {
                var tex = new Texture2D(w, h, TextureFormat.RGBA32, false) { wrapMode = TextureWrapMode.Clamp };
                tex.SetPixels(px);
                tex.Apply();
                return Sprite.Create(tex, new Rect(0, 0, w, h), new Vector2(0.5f, 0f), 64f / 0.5f);   // 64 px = 0.5 m wide
            }
            return (Make(cloth), Make(lines));
        }

        /// <summary>A served dish, turned so that the hall camera sees it from in front, as its art is drawn (the dishes
        /// are modelled for that view: seen from the side or the back they would look pulled out of shape).</summary>
        GameObject PlaceDish(Plate pl, TableSpot spot)
        {
            var prefab = Resources.Load<GameObject>("FoodModels/SM_" + pl.Dish.Id);
            if (prefab == null) return null;
            var f = cam.transform.forward;
            var facing = Quaternion.Euler(0, Mathf.Atan2(f.x, f.z) * Mathf.Rad2Deg, 0);
            var go = Instantiate(prefab, spot.Top, facing * prefab.transform.rotation, transform);
            go.name = "Served_" + pl.Dish.Id;
            return go;
        }

        /// <summary>
        /// The served dishes laid out on the table top: each in front of the guest who ordered it, next to the others
        /// along the table's edge, then pushed apart until none overlaps another or the cups and all are on the table;
        /// if they still crowd, all of them a little smaller. Each rests on the table's top, nothing through it.
        /// </summary>
        void LayOutTable(TableSpot spot)
        {
            var tableRect = spot.Rect;
            var tableThings = spot.Things;
            var items = spot.Served.Where(kv => kv.Value).Select(kv => (go: kv.Value, seat: spot.ServedSeat[kv.Key])).ToList();
            if (items.Count == 0) return;
            foreach (var (go, _) in items)   // at their full size first
            {
                var prefab = Resources.Load<GameObject>("FoodModels/SM_" + go.name.Substring("Served_".Length));
                if (prefab) go.transform.localScale = prefab.transform.localScale;
            }
            var reach = items.Select(x => FoodFit.Footprint(x.go).reach).ToArray();
            var c = tableRect.center;
            for (float k = 1f; ; k *= 0.9f)
            {
                var pos = new Vector2[items.Count];
                var r = reach.Select(x => x * k).ToArray();
                // where each would go: in front of its guest, side by side with the guest's other dishes
                foreach (var grp in Enumerable.Range(0, items.Count).GroupBy(i => items[i].seat))
                {
                    var d = new Vector2(grp.Key.x - c.x, grp.Key.z - c.y).normalized;
                    var side = new Vector2(-d.y, d.x);
                    var idx = grp.ToList();
                    float width = idx.Sum(i => 2 * r[i] + 0.02f), at = -width / 2;
                    float edge = Mathf.Abs(d.x) * tableRect.width / 2 + Mathf.Abs(d.y) * tableRect.height / 2;
                    foreach (var i in idx)
                    {
                        at += r[i] + 0.01f;
                        pos[i] = c + d * Mathf.Max(edge - r[i] - 0.03f, 0f) + side * at;
                        at += r[i] + 0.01f;
                    }
                }
                // pushed apart from each other and the cups, and kept on the table
                for (int it = 0; it < 60; it++)
                {
                    for (int i = 0; i < pos.Length; i++)
                    {
                        for (int j = i + 1; j < pos.Length; j++)
                        {
                            var v = pos[i] - pos[j];
                            float need = r[i] + r[j] + 0.015f, dist = v.magnitude;
                            if (dist >= need) continue;
                            var n = dist > 1e-4f ? v / dist : new Vector2(Mathf.Cos(i + j), Mathf.Sin(i + j));
                            pos[i] += n * (need - dist) / 2;
                            pos[j] -= n * (need - dist) / 2;
                        }
                        foreach (var (oc, or) in tableThings)
                        {
                            var v = pos[i] - oc;
                            float need = r[i] + or + 0.01f, dist = v.magnitude;
                            if (dist < need) pos[i] += (dist > 1e-4f ? v / dist : Vector2.right) * (need - dist);
                        }
                        pos[i] = new Vector2(Mathf.Clamp(pos[i].x, tableRect.xMin + r[i], tableRect.xMax - r[i]),
                                             Mathf.Clamp(pos[i].y, tableRect.yMin + r[i], tableRect.yMax - r[i]));
                    }
                }
                bool crowded = false;
                for (int i = 0; i < pos.Length && !crowded; i++)
                {
                    for (int j = i + 1; j < pos.Length; j++)
                        if ((pos[i] - pos[j]).magnitude < r[i] + r[j] + 0.005f) crowded = true;
                    foreach (var (oc, or) in tableThings)
                        if ((pos[i] - oc).magnitude < r[i] + or) crowded = true;
                }
                if (crowded && k > 0.5f) continue;
                for (int i = 0; i < items.Count; i++)
                {
                    var go = items[i].go;
                    var f = FoodFit.Footprint(go);
                    if (k < 1f) FoodFit.ScaleAbout(go, f.middle, k);
                    f = FoodFit.Footprint(go);
                    go.transform.position += new Vector3(pos[i].x - f.middle.x, spot.Top.y + 0.002f - f.bottom, pos[i].y - f.middle.z);
                }
                return;
            }
        }

        Bubble MakeBubble(string name, Vector3 at)
        {
            var go = new GameObject(name, typeof(Canvas));
            go.GetComponent<Canvas>().renderMode = RenderMode.WorldSpace;
            var b = new Bubble { Rt = (RectTransform)go.transform };
            b.Rt.SetParent(transform, false);
            b.Rt.sizeDelta = new Vector2(360, 104);
            b.Rt.position = at;
            var bg = UIKit.Rect(b.Rt, "Bg", Vector2.zero, Vector2.one);
            b.Bg = UIKit.Panel(bg, UIKit.Paper);
            var txt = UIKit.Rect(bg, "Text", new Vector2(0, 0.3f), Vector2.one);
            b.Text = UIKit.Label(txt, "", 40, UIKit.Ink, TextAnchor.MiddleCenter, FontStyle.Bold);
            var barBg = UIKit.Rect(bg, "Bar", new Vector2(0, 0), new Vector2(1, 0), new Vector2(20, 12), new Vector2(-20, 30));
            UIKit.Panel(barBg, new Color(0, 0, 0, 0.12f), false);
            var fillRt = UIKit.Rect(barBg, "Fill", Vector2.zero, Vector2.one);
            b.Bar = fillRt.gameObject.AddComponent<Image>();
            b.Bar.type = Image.Type.Filled;
            b.Bar.fillMethod = Image.FillMethod.Horizontal;
            b.Rt.gameObject.SetActive(false);
            return b;
        }
    }
}
