using System;
using System.Collections.Generic;
using System.Linq;
using BianHe.Core;
using UnityEngine;
using UnityEngine.UI;

namespace BianHe
{
    /// <summary>
    /// 集市采购 (《玩法与数值》06), before the shop opens: the market's stalls down the left (the vendors whose goods are on
    /// sale at this point; the seasonings, which the 面米铺 sells, on a stall card of their own), and the stall on show on
    /// the right, its goods one card each: the picture, how many the storeroom holds and which dishes use it, 普通 or 优质
    /// with each one's price, how many to buy, and what that comes to (a heap of ten or more of a main ingredient is
    /// cheaper, and comes bad a little more often). Each vendor can be asked once a day to come down (three ways to ask,
    /// each riskier for more). The order is bought all at once: the cost, and whether it fits the money and the
    /// storeroom, are at the bottom. Delivery is inspected at once (自动验货): the page says what was thrown out and what
    /// went on the shelf.
    /// </summary>
    public class MarketScreen : MonoBehaviour
    {
        public event Action Closed;
        public bool IsOpen => canvas && canvas.gameObject.activeSelf;

        const string Seasonings = "调料";        // the 面米铺's seasonings, on a stall card of their own

        /// <summary>A stall card on the left: the vendor (or 调料) it shows.</summary>
        class Stall
        {
            public string Key, Vendor;
            public Image Bg;
            public Text Name, Note;
        }

        /// <summary>A card for one of the goods: what it shows that changes.</summary>
        class Goods
        {
            public Ingredient Ing;
            public Text Have, Uses, Qty, Line;
            public Image Normal, Premium;
            public Text NormalText, PremiumText;
        }

        GameSession session;
        Canvas canvas;
        readonly List<Stall> stalls = new();
        readonly List<Goods> goods = new();
        string shown;                                                     // the stall on show
        readonly Dictionary<string, (Grade grade, int qty)> cart = new();  // by ingredient
        RectTransform stallList, goodsArea, bargainRow, report;
        Text info, vendorName, bargainNote, cartText, cartWarn, reportNote, reportLeft, reportRight, reportSum;
        Button buyButton;
        readonly List<Button> bargainButtons = new();

        static readonly Color Green = UIKit.Hex("#6f9a45");

        public void Build(GameSession s)
        {
            session = s;
            canvas = UIKit.Canvas("Market", 8);
            canvas.transform.SetParent(transform, false);
            var root = canvas.transform;

            var dim = UIKit.Rect(root, "Dim", Vector2.zero, Vector2.one);
            dim.gameObject.AddComponent<Image>().color = new Color(0.16f, 0.1f, 0.05f, 0.45f);   // blocks the hall behind it
            var page = UIKit.Rect(root, "Page", Vector2.zero, Vector2.one, new Vector2(60, 40), new Vector2(-60, -40));
            UIKit.Panel(page, UIKit.Paper);

            // the head: what the page is, the money and the storeroom, and the way back
            UIKit.Label(UIKit.Place(page, "Title", 40, 18, 360, 84), "集市采购", 52, UIKit.Ink, TextAnchor.MiddleLeft, FontStyle.Bold);
            info = UIKit.Label(UIKit.Place(page, "Info", 400, 18, 1060, 84), "", 30, UIKit.InkSoft, TextAnchor.MiddleLeft);
            var back = UIKit.Rect(page, "Back", new Vector2(1, 1), new Vector2(1, 1));
            back.pivot = new Vector2(1, 1);
            back.anchoredPosition = new Vector2(-30, -20);
            back.sizeDelta = new Vector2(230, 80);
            UIKit.Button(back, "回店里", 36, UIKit.Accent, Color.white, Close);

            stallList = UIKit.Place(page, "Stalls", 30, 120, 300, 740);
            goodsArea = UIKit.Place(page, "Goods", 360, 230, 1410, 640);

            // the stall on show and asking its vendor to come down
            vendorName = UIKit.Label(UIKit.Place(page, "Vendor", 360, 120, 300, 90), "", 44, UIKit.Ink, TextAnchor.MiddleLeft, FontStyle.Bold);
            bargainRow = UIKit.Place(page, "Bargain", 640, 125, 1130, 80);
            UIKit.Label(UIKit.Place(bargainRow, "Ask", 0, 0, 100, 80), "砍价", 32, UIKit.InkSoft, TextAnchor.MiddleLeft, FontStyle.Bold);
            var options = session.Data.Procurement.Bargains;
            for (int i = 0; i < options.Count; i++)
            {
                int k = i;
                var (line, cut, odds) = options[i];
                var b = UIKit.Place(bargainRow, "Option" + i, 100 + i * 343, 0, 335, 80);
                bargainButtons.Add(UIKit.Button(b, $"“{line}”\n{Pct(cut)} · {Chance(odds)}", 24, UIKit.Card, UIKit.Ink, () => Bargain(k)));
            }
            bargainNote = UIKit.Label(UIKit.Place(bargainRow, "Note", 100, 0, 1020, 80), "", 30, UIKit.Ink, TextAnchor.MiddleLeft);

            // the order: what it holds, what it costs, what stands in the way; 清空 and 买下
            var foot = UIKit.Rect(page, "Foot", new Vector2(0, 0), new Vector2(1, 0), new Vector2(30, 20), new Vector2(-30, 120));
            UIKit.Panel(foot, UIKit.Card, false);
            cartText = UIKit.Label(UIKit.Rect(foot, "Cart", new Vector2(0, 0.42f), new Vector2(0.68f, 1)), "", 28, UIKit.Ink, TextAnchor.MiddleLeft);
            cartWarn = UIKit.Label(UIKit.Rect(foot, "Warn", new Vector2(0, 0), new Vector2(0.68f, 0.45f)), "", 26, UIKit.Fire, TextAnchor.MiddleLeft);
            var clear = UIKit.Rect(foot, "Clear", new Vector2(0.7f, 0.15f), new Vector2(0.83f, 0.85f));
            UIKit.Button(clear, "清空", 34, UIKit.Paper, UIKit.Ink, () => { cart.Clear(); Refresh(); });
            var buy = UIKit.Rect(foot, "Buy", new Vector2(0.845f, 0.12f), new Vector2(0.99f, 0.88f));
            buyButton = UIKit.Button(buy, "买下", 40, UIKit.Accent, Color.white, Buy);
            var cb = buyButton.colors;
            cb.disabledColor = Color.white;   // its colour is set by hand
            buyButton.colors = cb;

            // delivery and inspection, over the page: how inspection goes, a line per thing bought (in two columns when
            // there are many), what it cost
            report = UIKit.Rect(root, "Report", new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f));
            report.sizeDelta = new Vector2(1500, 860);
            UIKit.Panel(report, UIKit.Paper);
            UIKit.Label(UIKit.Rect(report, "Title", new Vector2(0, 1), new Vector2(1, 1), new Vector2(0, -100), new Vector2(0, -16)), "到货验货", 50, UIKit.Ink, TextAnchor.MiddleCenter, FontStyle.Bold);
            reportNote = UIKit.Label(UIKit.Place(report, "Note", 60, 100, 1380, 50), "", 26, UIKit.InkSoft);
            reportLeft = UIKit.Label(UIKit.Place(report, "Left", 60, 165, 680, 470), "", 28, UIKit.Ink, TextAnchor.UpperLeft);
            reportRight = UIKit.Label(UIKit.Place(report, "Right", 760, 165, 680, 470), "", 28, UIKit.Ink, TextAnchor.UpperLeft);
            reportLeft.lineSpacing = reportRight.lineSpacing = 1.2f;
            reportSum = UIKit.Label(UIKit.Place(report, "Sum", 60, 645, 1380, 56), "", 32, UIKit.Ink, TextAnchor.MiddleCenter, FontStyle.Bold);
            var ok = UIKit.Rect(report, "Ok", new Vector2(0.5f, 0), new Vector2(0.5f, 0));
            ok.pivot = new Vector2(0.5f, 0);
            ok.anchoredPosition = new Vector2(0, 30);
            ok.sizeDelta = new Vector2(240, 84);
            UIKit.Button(ok, "好", 40, UIKit.Accent, Color.white, () => report.gameObject.SetActive(false));
            report.gameObject.SetActive(false);

            canvas.gameObject.SetActive(false);
        }

        // ------------------------------------------------------------------ open / close

        public void Open()
        {
            if (IsOpen) return;
            canvas.gameObject.SetActive(true);
            report.gameObject.SetActive(false);
            BuildStalls();
            if (shown == null || stalls.All(st => st.Key != shown)) shown = stalls.FirstOrDefault()?.Key;
            ShowStall(shown);
        }

        public void Close()
        {
            if (!IsOpen) return;
            canvas.gameObject.SetActive(false);
            Closed?.Invoke();
        }

        /// <summary>The stall cards: the vendors with goods on sale now, in the data's order, the seasonings after the 面米铺.</summary>
        void BuildStalls()
        {
            foreach (Transform c in stallList) Destroy(c.gameObject);
            stalls.Clear();
            var keys = new List<(string key, string vendor)>();
            foreach (var g in session.MarketGoods())
            {
                if (g.Any(i => !i.IsSeasoning)) keys.Add((g.Key, g.Key));
                if (g.Any(i => i.IsSeasoning)) keys.Add((Seasonings, g.Key));
            }
            float h = Mathf.Min(92, (750 - (keys.Count - 1) * 10) / (float)Mathf.Max(1, keys.Count));
            for (int k = 0; k < keys.Count; k++)
            {
                var st = new Stall { Key = keys[k].key, Vendor = keys[k].vendor };
                var rt = UIKit.Place(stallList, "Stall_" + st.Key, 0, k * (h + 10), 300, h);
                var btn = UIKit.Button(rt, null, 0, UIKit.Card, UIKit.Ink, () => ShowStall(st.Key));
                st.Bg = (Image)btn.targetGraphic;
                st.Name = UIKit.Label(UIKit.Rect(rt, "Name", new Vector2(0, 0.42f), Vector2.one, new Vector2(18, 0), Vector2.zero), st.Key, 34, UIKit.Ink, TextAnchor.MiddleLeft, FontStyle.Bold);
                st.Note = UIKit.Label(UIKit.Rect(rt, "Note", Vector2.zero, new Vector2(1, 0.48f), new Vector2(18, 4), Vector2.zero), "", 22, UIKit.InkSoft, TextAnchor.MiddleLeft);
                stalls.Add(st);
            }
        }

        IEnumerable<Ingredient> GoodsOf(string key)
        {
            if (key == null) return Enumerable.Empty<Ingredient>();
            var vendor = VendorOf(key);
            return session.MarketGoods().Where(g => g.Key == vendor).SelectMany(g => g).Where(i => i.IsSeasoning == (key == Seasonings));
        }

        string VendorOf(string key) => stalls.FirstOrDefault(st => st.Key == key)?.Vendor ?? key;

        /// <summary>The goods of a stall, a card each, four to a row.</summary>
        void ShowStall(string key)
        {
            shown = key;
            foreach (Transform c in goodsArea) Destroy(c.gameObject);
            goods.Clear();
            var list = GoodsOf(key).ToList();
            int rows = Mathf.Max(1, (list.Count + 3) / 4);
            float w = (1410 - 3 * 18) / 4f, h = Mathf.Min(300, (640 - (rows - 1) * 16) / (float)rows);
            for (int n = 0; n < list.Count; n++)
                goods.Add(BuildCard(list[n], (n % 4) * (w + 18), (n / 4) * (h + 16), w, h));
            vendorName.text = key == Seasonings ? $"{key}（{VendorOf(key)}）" : key;
            Refresh();
        }

        Goods BuildCard(Ingredient ing, float x, float y, float w, float h)
        {
            var g = new Goods { Ing = ing };
            var card = UIKit.Place(goodsArea, "Card_" + ing.Id, x, y, w, h);
            UIKit.Panel(card, UIKit.Card, false);
            float pic = Mathf.Min(104, h * 0.36f);
            var sprite = Resources.Load<Sprite>("Food3D/" + ing.Id) ?? Resources.Load<Sprite>("Food/" + ing.Id);
            var img = UIKit.Img(card, "Pic", sprite, Color.white, new Vector2(0, 1), new Vector2(0, 1), preserveAspect: true);
            img.rectTransform.pivot = new Vector2(0, 1);
            img.rectTransform.anchoredPosition = new Vector2(12, -10);
            img.rectTransform.sizeDelta = new Vector2(pic, pic);
            UIKit.Label(UIKit.Place(card, "Name", pic + 20, 8, w - pic - 28, 46), ing.Name, 32, UIKit.Ink, TextAnchor.MiddleLeft, FontStyle.Bold);
            g.Have = UIKit.Label(UIKit.Place(card, "Have", pic + 20, 52, w - pic - 28, 30), "", 24, UIKit.InkSoft, TextAnchor.MiddleLeft);
            g.Uses = UIKit.Label(UIKit.Place(card, "Uses", pic + 20, 80, w - pic - 28, 30), "", 20, UIKit.InkSoft, TextAnchor.MiddleLeft);

            // 普通 / 优质, each with its price for this many
            float row = pic + 18;
            if (ing.HasPremium)
            {
                var n = UIKit.Place(card, "Normal", 12, row, (w - 36) / 2, 44);
                var nb = UIKit.Button(n, null, 0, UIKit.Paper, UIKit.Ink, () => SetGrade(ing, Grade.Normal));
                g.Normal = (Image)nb.targetGraphic;
                g.NormalText = UIKit.Label(n, "", 24, UIKit.Ink);
                var pr = UIKit.Place(card, "Premium", 24 + (w - 36) / 2, row, (w - 36) / 2, 44);
                var pb = UIKit.Button(pr, null, 0, UIKit.Paper, UIKit.Ink, () => SetGrade(ing, Grade.Premium));
                g.Premium = (Image)pb.targetGraphic;
                g.PremiumText = UIKit.Label(pr, "", 24, UIKit.Ink);
            }
            else
                g.NormalText = UIKit.Label(UIKit.Place(card, "Price", 12, row, w - 24, 44), "", 24, UIKit.Ink, TextAnchor.MiddleLeft);

            // how many: −, the count, +, +10
            float q = row + 52, bw = (w - 24 - 3 * 8) / 4;
            UIKit.Button(UIKit.Place(card, "Less", 12, q, bw, 50), "−", 34, UIKit.Paper, UIKit.Ink, () => Add(ing, -1));
            var qty = UIKit.Place(card, "Qty", 12 + (bw + 8), q, bw, 50);
            UIKit.Panel(qty, Color.white, false);
            g.Qty = UIKit.Label(qty, "0", 30, UIKit.Ink, TextAnchor.MiddleCenter, FontStyle.Bold);
            UIKit.Button(UIKit.Place(card, "More", 12 + 2 * (bw + 8), q, bw, 50), "+", 34, UIKit.Paper, UIKit.Ink, () => Add(ing, 1));
            UIKit.Button(UIKit.Place(card, "Ten", 12 + 3 * (bw + 8), q, bw, 50), "+10", 28, UIKit.Paper, UIKit.Ink, () => Add(ing, 10));
            g.Line = UIKit.Label(UIKit.Place(card, "Line", 12, q + 54, w - 24, Mathf.Max(28, h - q - 58)), "", 21, UIKit.InkSoft, TextAnchor.MiddleLeft);
            return g;
        }

        // ------------------------------------------------------------------ actions

        void SetGrade(Ingredient ing, Grade grade)
        {
            cart.TryGetValue(ing.Id, out var c);
            cart[ing.Id] = (grade, c.qty);
            Refresh();
        }

        void Add(Ingredient ing, int n)
        {
            cart.TryGetValue(ing.Id, out var c);
            cart[ing.Id] = (c.grade, Mathf.Max(0, c.qty + n));
            Refresh();
        }

        void Bargain(int option)
        {
            var vendor = VendorOf(shown);
            if (vendor == null || session.Market.Asked(vendor)) return;
            session.Bargain(vendor, option);
            Refresh();
        }

        List<OrderLine> Order() =>
            cart.Where(kv => kv.Value.qty > 0).Select(kv => new OrderLine { Id = kv.Key, Grade = kv.Value.grade, Qty = kv.Value.qty }).ToList();

        void Buy()
        {
            var order = Order();
            var got = session.BuyFood(order);
            if (got == null) { Refresh(); return; }
            int cost = got.Sum(a => a.UnitPrice * a.Bought);
            cart.Clear();
            var lines = got.Select(a =>
            {
                var ing = session.Data.Ingredients[a.Id];
                string what = $"{ing.Name}{(ing.HasPremium ? (a.Grade == Grade.Premium ? "（优质）" : "（普通）") : "")} {a.Bought} 份";
                return a.Found > 0 ? $"{what}：挑出坏料 {a.Found} 份丢掉，入库 {a.Kept}"
                     : session.Pantry.BadRate(ing, a.Grade, a.Bought) > 0 ? $"{what}：没挑出坏料，入库 {a.Kept}" : $"{what}：入库 {a.Kept}";
            }).ToList();
            int half = lines.Count > 9 ? (lines.Count + 1) / 2 : lines.Count;   // two columns when there are many
            reportLeft.text = string.Join("\n", lines.Take(half));
            reportRight.text = string.Join("\n", lines.Skip(half));
            reportNote.text = session.AutoInspect
                ? "自动验货：坏料挑出来丢掉；约有二十分之一会漏掉，出锅时才发现，那份作废"
                : "坏料要自己挑出来丢掉；漏掉的出锅时才发现，那份作废";
            reportSum.text = $"花了 {Wen(cost)} 文，还剩 {Wen(session.Cash)} 文";
            report.gameObject.SetActive(true);
            Refresh();
        }

        // ------------------------------------------------------------------ what the page shows

        void Refresh()
        {
            var data = session.Data;
            var stage = session.Stage;
            var order = Order();
            int cost = session.Pantry.Total(order, session.Market.Discount);
            int mainsAfter = session.Pantry.MainCount + session.MainPortions(order);
            info.text = $"钱 {Wen(session.Cash)} 文　·　库存（主料）{session.Pantry.MainCount} / {stage.InventoryCap} 份　·　{(session.AutoInspect ? "自动验货" : "到货自己验")}";

            foreach (var st in stalls)
            {
                bool on = st.Key == shown;
                st.Bg.color = on ? UIKit.Accent : UIKit.Card;
                st.Name.color = on ? Color.white : UIKit.Ink;
                double d = session.Market.Discount(st.Vendor);
                int inCart = order.Where(l => data.Ingredients[l.Id].Vendor == st.Vendor && data.Ingredients[l.Id].IsSeasoning == (st.Key == Seasonings)).Sum(l => l.Qty);
                string asked = d > 0 ? $"砍成了{Pct(d)}" : session.Market.Asked(st.Vendor) ? "没砍下来" : "";
                st.Note.text = string.Join("　", new[] { asked, inCart > 0 ? $"这趟 {inCart} 份" : "" }.Where(x => x != ""));
                st.Note.color = on ? Color.white : UIKit.InkSoft;
            }

            var vendor = VendorOf(shown);
            bool askedHere = vendor != null && session.Market.Asked(vendor);
            foreach (var b in bargainButtons) b.gameObject.SetActive(!askedHere && vendor != null);
            double cut = session.Market.Discount(vendor);
            bargainNote.text = !askedHere ? "" : cut > 0 ? $"砍成了：{vendor}今天的东西都{Pct(cut)}" : $"没砍下来：{vendor}今天按原价，不再讲价";
            bargainNote.color = cut > 0 ? Green : UIKit.InkSoft;

            foreach (var g in goods)
            {
                var ing = g.Ing;
                cart.TryGetValue(ing.Id, out var c);
                int qty = c.qty, n = Mathf.Max(1, qty);
                double bargain = session.Market.Discount(ing.Vendor);
                int have = session.Pantry.Count(ing.Id), haveP = session.Pantry.Count(ing.Id, Grade.Premium);
                g.Have.text = ing.HasPremium && haveP > 0 ? $"库存 {have} 份（优质 {haveP}）" : $"库存 {have} 份";
                var uses = session.DishesUsing(ing.Id).Select(r => r.Name).ToList();
                g.Uses.text = uses.Count > 0 ? "做" + string.Join("、", uses) : "暂时用不上";
                int pn = session.Pantry.UnitPrice(ing, Grade.Normal, n, bargain);
                if (ing.HasPremium)
                {
                    int pp = session.Pantry.UnitPrice(ing, Grade.Premium, n, bargain);
                    bool prem = c.grade == Grade.Premium;
                    g.Normal.color = prem ? UIKit.Paper : UIKit.Accent;
                    g.Premium.color = prem ? UIKit.Accent : UIKit.Paper;
                    g.NormalText.text = $"普通 {Wen(pn)} 文";
                    g.PremiumText.text = $"优质 {Wen(pp)} 文";
                    g.NormalText.color = prem ? UIKit.Ink : Color.white;
                    g.PremiumText.color = prem ? Color.white : UIKit.Ink;
                }
                else g.NormalText.text = $"{Wen(pn)} 文一份";
                g.Qty.text = qty.ToString();
                // what this line comes to, and what goes with it: the heap discount, how often it comes bad
                int unit = session.Pantry.UnitPrice(ing, c.grade, n, bargain);
                double bad = session.Pantry.BadRate(ing, c.grade, n);
                var notes = new List<string>();
                if (qty > 0) notes.Add($"小计 {Wen(unit * qty)} 文");
                if (c.grade == Grade.Normal && ing.IsMain && ing.Source == "market")
                    notes.Add(qty >= 20 ? "整筐八折" : qty >= 10 ? "满十份九折" : "十份起九折");
                if (bad > 0) notes.Add($"坏料约 {Math.Round(bad * 100)}%");
                if (!ing.IsMain) notes.Add(ing.IsSeasoning ? "调料不占库存" : "不占库存");
                g.Line.text = string.Join(" · ", notes);
            }

            // the order as a whole: what it holds, what it costs, what stands in the way
            cartText.text = order.Count == 0 ? "还没选东西：点各样东西下面的“+”"
                : "这趟：" + string.Join("、", order.Select(l => $"{data.IngredientName(l.Id)}{(l.Grade == Grade.Premium ? "（优）" : "")} {l.Qty}"))
                  + $"　共 {Wen(cost)} 文";
            string warn = cost > session.Cash ? $"钱不够：还差 {Wen(cost - session.Cash)} 文"
                        : mainsAfter > stage.InventoryCap ? $"库存放不下：主料会到 {mainsAfter} / {stage.InventoryCap} 份"
                        : order.Count > 0 ? $"买下后库存（主料）{mainsAfter} / {stage.InventoryCap} 份" : "";
            cartWarn.text = warn;
            cartWarn.color = cost > session.Cash || mainsAfter > stage.InventoryCap ? UIKit.Fire : UIKit.InkSoft;
            bool ok = order.Count > 0 && cost <= session.Cash && mainsAfter <= stage.InventoryCap;
            buyButton.interactable = ok;
            buyButton.image.color = ok ? UIKit.Accent : UIKit.Locked;
        }

        /// <summary>Money in 文 from 1/100 文: whole 文 plainly, else with the fraction.</summary>
        public static string Wen(int cents) => cents % 100 == 0 ? (cents / 100).ToString() : (cents / 100.0).ToString("0.##");

        /// <summary>A price cut as the market says it: 九五折, 九折, 八折.</summary>
        static string Pct(double cut)
        {
            int k = (int)Math.Round((1 - cut) * 100);
            string[] digits = { "零", "一", "二", "三", "四", "五", "六", "七", "八", "九" };
            return k % 10 == 0 ? digits[k / 10] + "折" : digits[k / 10] + digits[k % 10] + "折";
        }

        /// <summary>How likely a way of asking works: 九成, 六成, 三成.</summary>
        static string Chance(double p)
        {
            string[] digits = { "零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十" };
            return digits[(int)Math.Round(p * 10)] + "成能成";
        }

        // ------------------------------------------------------------------ for the screenshot run

        /// <summary>For the screenshots: show a stall (by its card's name), put things in the order, ask the vendor down.</summary>
        public void DemoShow(string key) => ShowStall(key);
        public void DemoAdd(string id, int n, Grade grade = Grade.Normal)
        {
            var ing = session.Data.Ingredients[id];
            SetGrade(ing, grade);
            Add(ing, n);
        }
        public void DemoBargain(int option) => Bargain(option);
        public void DemoBuy() => Buy();
        public IEnumerable<string> DemoStalls => stalls.Select(st => st.Key);
    }
}
