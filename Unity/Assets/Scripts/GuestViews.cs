using System.Collections.Generic;
using System.Linq;
using BianHe.Core;
using UnityEngine;
using UnityEngine.UI;

namespace BianHe
{
    /// <summary>
    /// Stand-in 纸片人 for the guests until the real cut-outs are drawn: flat cards that always face the
    /// camera, seated on the stools of 1 号桌 or queueing by the steps, plus a bubble over the table
    /// with the table's state (等菜 with the patience left, 催单, 用餐, the bill).
    /// </summary>
    public class GuestViews : MonoBehaviour
    {
        Camera cam;
        readonly List<Vector3> seats = new();
        readonly List<Vector3> doorSpots = new();
        Vector3 tableTop;
        readonly Dictionary<Guest, (SpriteRenderer clothes, SpriteRenderer lines)> dolls = new();
        readonly Dictionary<Plate, GameObject> served = new();   // 3D dishes on the table
        RectTransform bubble;
        Text bubbleText;
        Image bubbleBg, bubbleBar;
        string flash;
        float flashUntil;

        static (Sprite clothes, Sprite lines) sitting, standing;
        static readonly Color[] Clothes = { UIKit.Hex("#5d7fa6"), UIKit.Hex("#9b6a45"), UIKit.Hex("#7d8f6a"), UIKit.Hex("#c49a52"), UIKit.Hex("#8a5f7a") };

        public void Setup(Transform level, Camera camera)
        {
            cam = camera;
            var all = level.GetComponentsInChildren<Transform>(true);
            Vector3 Top(Transform t)
            {
                var b = new Bounds(t.position, Vector3.zero);
                foreach (var r in t.GetComponentsInChildren<Renderer>()) b.Encapsulate(r.bounds);
                return new Vector3(b.center.x, b.max.y, b.center.z);
            }
            foreach (var n in new[] { "D_Stool_1", "D_Stool_2", "D_Stool_3", "D_Stool_4" })
            {
                var t = all.FirstOrDefault(x => x.name == n);
                if (t) seats.Add(Top(t));
            }
            var table = all.FirstOrDefault(x => x.name == "D_Table_1");
            tableTop = table ? Top(table) : Vector3.up;
            // queue spots are empties in the white model (Spot_Queue_1…4, on the stepping stones)
            foreach (var t in all.Where(x => x.name.StartsWith("Spot_Queue_")).OrderBy(x => x.name))
                doorSpots.Add(t.position);
            if (doorSpots.Count == 0) doorSpots.Add(tableTop + new Vector3(0, -tableTop.y, -3f));
            BuildBubble();
        }

        public void Flash(string msg)
        {
            flash = msg;
            flashUntil = Time.time + 2.5f;
        }

        public void Sync(Service service, long now)
        {
            var live = new HashSet<Guest>();
            Party seated = null, door = null;
            foreach (var p in service.Parties)
            {
                if (p.State is PartyState.Waiting or PartyState.Dining) seated = p;
                else if (p.State == PartyState.AtDoor) door = p;
                else continue;
                for (int i = 0; i < p.Guests.Count; i++)
                {
                    var g = p.Guests[i];
                    live.Add(g);
                    bool sit = p.State != PartyState.AtDoor;
                    var d = Doll(g, sit);
                    d.clothes.transform.parent.position = sit ? seats[i % seats.Count] : doorSpots[i % doorSpots.Count];
                }
            }
            // served dishes sit on the table in front of whoever ordered them
            var livePlates = new HashSet<Plate>();
            if (seated != null)
                for (int i = 0; i < seated.Guests.Count; i++)
                {
                    var plates = seated.Guests[i].Plates;
                    for (int j = 0; j < plates.Count; j++)
                    {
                        var pl = plates[j];
                        if (!pl.Served) continue;
                        livePlates.Add(pl);
                        if (!served.ContainsKey(pl)) served[pl] = PlaceDish(pl, seats[i % seats.Count], j);
                    }
                }
            foreach (var pl in served.Keys.Where(pl => !livePlates.Contains(pl)).ToList())
            {
                if (served[pl]) Destroy(served[pl]);
                served.Remove(pl);
            }

            foreach (var g in dolls.Keys.Where(g => !live.Contains(g)).ToList())
            {
                Destroy(dolls[g].clothes.transform.parent.gameObject);
                dolls.Remove(g);
            }

            // table bubble
            string text = null;
            Color bg = UIKit.Paper, fg = UIKit.Ink;
            float bar = -1;
            if (Time.time < flashUntil) { text = flash; bg = UIKit.Good; fg = Color.white; }
            else if (seated != null && seated.State == PartyState.Waiting)
            {
                long left = seated.OrderedMs + seated.PatienceMs - now;
                int todo = seated.Plates.Count(pl => !pl.Served);
                if (!seated.Late) { text = $"等菜 {todo} 份 · {CookRules.Seconds(left)}秒"; bar = Mathf.Clamp01(left / (float)seated.PatienceMs); }
                else { text = $"催单！还剩 {CookRules.Seconds(seated.LeaveAtMs - now)}秒"; bg = UIKit.Hex("#c0462c"); fg = Color.white; bar = Mathf.Clamp01((seated.LeaveAtMs - now) / (float)ServiceRules.LeaveAfterLateMs); }
            }
            else if (seated != null) text = "用餐中";
            else if (door != null) text = $"门口有 {door.Guests.Count} 位客人在等";
            bubble.gameObject.SetActive(text != null);
            if (text != null)
            {
                bubbleText.text = text;
                bubbleText.color = fg;
                bubbleBg.color = bg;
                bubbleBar.transform.parent.gameObject.SetActive(bar >= 0);
                bubbleBar.fillAmount = Mathf.Max(0, bar);
                bubbleBar.color = bar > 0.35f ? UIKit.Good : UIKit.Fire;
            }
        }

        void LateUpdate()
        {
            if (!cam) return;
            foreach (var d in dolls.Values) d.clothes.transform.parent.rotation = cam.transform.rotation;
            if (bubble)
            {
                bubble.rotation = cam.transform.rotation;
                bubble.localScale = Vector3.one * 0.0042f * Mathf.Clamp(cam.orthographicSize / 4f, 0.6f, 1.6f);
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
                dolls[g] = d;
            }
            if (sit && sitting.clothes == null) sitting = MakeDoll(0.0f);
            if (!sit && standing.clothes == null) standing = MakeDoll(1.6f);
            var s = sit ? sitting : standing;
            d.clothes.sprite = s.clothes;
            d.lines.sprite = s.lines;
            return d;
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

        GameObject PlaceDish(Plate pl, Vector3 seat, int k)
        {
            var prefab = Resources.Load<GameObject>("FoodModels/SM_" + pl.Dish.Id);
            if (prefab == null) return null;
            var toSeat = seat - tableTop;
            toSeat.y = 0;
            var dir = toSeat.normalized;
            var side = Vector3.Cross(Vector3.up, dir);
            var pos = tableTop + dir * 0.27f + side * (k == 0 ? -0.05f : 0.14f);
            pos.y = tableTop.y - 0.06f;   // table top, below the cups
            var go = Instantiate(prefab, pos, Quaternion.LookRotation(-dir) * prefab.transform.rotation, transform);
            go.name = "Served_" + pl.Dish.Id;
            return go;
        }

        void BuildBubble()
        {
            var go = new GameObject("TableBubble", typeof(Canvas));
            go.GetComponent<Canvas>().renderMode = RenderMode.WorldSpace;
            bubble = (RectTransform)go.transform;
            bubble.SetParent(transform, false);
            bubble.sizeDelta = new Vector2(460, 120);
            bubble.position = tableTop + Vector3.up * 1.35f;
            var bg = UIKit.Rect(bubble, "Bg", Vector2.zero, Vector2.one);
            bubbleBg = UIKit.Panel(bg, UIKit.Paper);
            var txt = UIKit.Rect(bg, "Text", new Vector2(0, 0.3f), Vector2.one);
            bubbleText = UIKit.Label(txt, "", 44, UIKit.Ink, TextAnchor.MiddleCenter, FontStyle.Bold);
            var barBg = UIKit.Rect(bg, "Bar", new Vector2(0, 0), new Vector2(1, 0), new Vector2(24, 14), new Vector2(-24, 34));
            UIKit.Panel(barBg, new Color(0, 0, 0, 0.12f), false);
            var fillRt = UIKit.Rect(barBg, "Fill", Vector2.zero, Vector2.one);
            bubbleBar = fillRt.gameObject.AddComponent<Image>();
            bubbleBar.type = Image.Type.Filled;
            bubbleBar.fillMethod = Image.FillMethod.Horizontal;
            bubble.gameObject.SetActive(false);
        }
    }
}
