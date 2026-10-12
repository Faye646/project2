using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using BianHe.Core;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem.UI;
using UnityEngine.UI;

namespace BianHe
{
    /// <summary>
    /// 初始·1桌 demo flow. The shop floor is a pannable, zoomable 3D view; tapping the 案台 switches
    /// to the flat cooking screen, and 返回前堂 switches back. While the cooking screen is up the 3D
    /// camera draws nothing, so the two screens never overlap. The hall HUD runs the business day:
    /// 开门前 → 营业 (6 minutes) → 打烊结算 → next day.
    ///
    /// The shop grows with the 声望 stage: shops[0] is 初始·1桌, shops[1…5] the shop at 一级 … 五级 (build_shop.py); the day
    /// after an upgrade opens in the new shop. Its tables are bought one at a time, and the 二楼 with the 雅间 is paid for
    /// once (《玩法与数值》04 桌椅与扩建; Premises): the 添置 page, or a tap on the next table standing as a sketch.
    ///
    /// Run a player with  -shots &lt;folder&gt;  to save the demo screenshots there and quit;  -stage &lt;id&gt;  (1_1, 1_2, 1_3, 2 … 5)
    /// starts at that stage, with every table it allows bought;  -own &lt;n&gt;  makes it the first n tables instead (6 and up:
    /// the 二楼 among them, open);  -cash &lt;文&gt;  sets the money;  -shopshot &lt;folder&gt;  photographs that stage's shop with
    /// every table taken, then quits;  -buyshots &lt;folder&gt;  photographs buying the next table or the 二楼, then quits.
    /// </summary>
    public class GameFlow : MonoBehaviour
    {
        public CameraRig rig;
        public Transform level;     // the shop on show (one of shops)
        public Transform[] shops;   // 初始, 一级 … 五级 (missing ones null: the nearest lower one stands in)
        public Transform cookSet;   // the 3D kitchen counter set the cooking screen looks at
        public string stationName = "K_AnTai";

        GameSession session;
        CookingScreen cooking;
        CookStation station;
        Canvas hud;
        GuestViews guests;
        ShopFloor floor;
        Text titleText, statusText, noticeText;
        float noticeUntil;
        Text dayText;
        Button dayButton;
        Text dayButtonText;
        RectTransform settlement;
        Text settlementText;
        int sceneMask;
        Vector3 homeCenter;
        float homeSize;
        int shopIndex = -1;
        bool building;              // a bought table popping in or the 二楼 going up: hands off meanwhile
        int panelCash;              // the money the 添置 page last showed

        // 添置桌椅: the button under 全景 (a dot on it when something can be bought now) and its page
        RectTransform buyButton, shopPanel;
        GameObject buyDot;
        Text panelSummary, offerName, offerDetail, offerPrice, offerHint, offerButtonText, upstairsNote;
        Button offerButton;
        readonly List<(int table, Image cell, Text label)> mapCells = new();

        void Start()
        {
            Application.targetFrameRate = 60;
            if (EventSystem.current == null)
                new GameObject("EventSystem", typeof(EventSystem), typeof(InputSystemUIInputModule));

            session = new GameSession();
            var args = System.Environment.GetCommandLineArgs();
            string Arg(string name)
            {
                int k = System.Array.IndexOf(args, name);
                return k >= 0 && k + 1 < args.Length ? args[k + 1] : null;
            }
            if (Arg("-stage") is { } stageId)
            {
                var stage = session.Data.Stages.FirstOrDefault(x => x.Id == stageId);
                if (stage != null)
                {
                    session.Xp = stage.Xp;
                    session.Premises.Grant(stage.TableCap, session.Day.Day);   // as if every table it allows were bought
                }
                else Debug.LogError($"GameFlow: no stage '{stageId}'");
            }
            if (int.TryParse(Arg("-own"), out int own)) session.Premises.Grant(own, session.Day.Day);
            if (int.TryParse(Arg("-cash"), out int cash)) session.Cash = cash * 100;
            session.OpenStoves();   // the stove blocks of the stage started at
            if (shops == null || shops.Length == 0) shops = new[] { level };

            guests = new GameObject("Guests").AddComponent<GuestViews>();
            floor = new GameObject("ShopFloor").AddComponent<ShopFloor>();
            session.Service.Notice += Notice;

            cooking = new GameObject("Cooking").AddComponent<CookingScreen>();
            cooking.Build(session, cookSet);
            cooking.Closed += OnCookingClosed;

            rig.Tapped += OnTap;
            sceneMask = rig.Cam.cullingMask;
            ApplyStage();
            BuildHud();

            if (Arg("-shots") is { } shots) StartCoroutine(TakeShots(shots));
            if (Arg("-shopshot") is { } shopShots) StartCoroutine(ShopShot(shopShots));
            if (Arg("-buyshots") is { } buyShots) StartCoroutine(BuyShots(buyShots));
            if (Arg("-stoveshots") is { } stoveShots) StartCoroutine(StoveShots(stoveShots));
            if (System.Array.IndexOf(args, "-video") >= 0) StartCoroutine(PlayForVideo());
            int w = System.Array.IndexOf(args, "-wok");
            if (w >= 0 && w + 1 < args.Length)
                StartCoroutine(WokShots(args[w + 1], w + 2 < args.Length && !args[w + 2].StartsWith("-") ? args[w + 2] : "D08"));
        }

        /// <summary>Which shop a stage keeps: 初始·1桌 for 一级①, the 一级 shop for ②③, then one per level.</summary>
        static int ShopFor(StageInfo s) => s.Id switch { "1_1" => 0, "1_2" or "1_3" => 1, "2" => 2, "3" => 3, "4" => 4, "5" => 5, _ => 0 };

        /// <summary>The shop for the current stage on show, with the tables bought standing in it and the next one for sale
        /// as a sketch; the camera framed on it afresh when the shop changed.</summary>
        void ApplyStage()
        {
            bool changed = UseShop(ShopFor(session.Stage));
            session.TablesInModel = guests.TableCount;
            ShowFloor();
            FitRig(changed);
        }

        /// <summary>The shop's furniture as bought, and the next thing for sale.</summary>
        void ShowFloor() => floor.Show(session.Premises, session.NextOffer, session.Day.Day);

        bool UseShop(int idx)
        {
            idx = Mathf.Clamp(idx, 0, shops.Length - 1);
            while (idx > 0 && shops[idx] == null) idx--;
            if (idx == shopIndex) return false;
            shopIndex = idx;
            for (int k = 0; k < shops.Length; k++)
                if (shops[k]) shops[k].gameObject.SetActive(k == idx);
            level = shops[idx];
            var st = FindDeep(level, stationName);
            station = st ? st.GetComponent<CookStation>() : null;
            if (st && !station)
            {
                station = st.gameObject.AddComponent<CookStation>();
                station.Setup(rig.Cam);
            }
            if (!st) Debug.LogError($"GameFlow: no '{stationName}' under {level.name}");
            guests.Setup(level, rig.Cam);   // (everything in the new shop still stands: its tables are measured whole)
            floor.Setup(level, rig.Cam);
            return true;
        }

        /// <summary>Clamp and zoom limits from what of the shop stands (a sketch included), and with `frame` the whole of it on show.</summary>
        void FitRig(bool frame)
        {
            var b = new Bounds(level.position, Vector3.zero);
            var parts = level.GetComponentsInChildren<Renderer>();
            foreach (var r in parts) b.Encapsulate(r.bounds);
            rig.bounds = new Rect(b.min.x, b.min.z, b.size.x, b.size.z);

            // the shop as the camera sees it: the corners of each part's box in view space (not the corners of the
            // whole shop's box, whose empty corners would push an L-shaped shop off the middle of the screen)
            var rot = Quaternion.Euler(rig.pitch, rig.yaw, 0);
            var inv = Quaternion.Inverse(rot);
            float x0 = float.MaxValue, x1 = float.MinValue, y0 = float.MaxValue, y1 = float.MinValue;
            foreach (var r in parts)
            {
                var rb = r.bounds;
                for (int k = 0; k < 8; k++)
                {
                    var corner = new Vector3((k & 1) == 0 ? rb.min.x : rb.max.x, (k & 2) == 0 ? rb.min.y : rb.max.y, (k & 4) == 0 ? rb.min.z : rb.max.z);
                    var v = inv * corner;
                    x0 = Mathf.Min(x0, v.x); x1 = Mathf.Max(x1, v.x);
                    y0 = Mathf.Min(y0, v.y); y1 = Mathf.Max(y1, v.y);
                }
            }
            if (x0 > x1) { x0 = x1 = y0 = y1 = 0; }
            float aspect = (float)Screen.width / Screen.height;
            // room above and below for the HUD (the title and the day's bar at the top, the hint at the bottom)
            homeSize = Mathf.Max((y1 - y0) / 2 * 1.3f, (x1 - x0) / 2 / aspect * 1.08f);
            rig.maxSize = homeSize * 1.15f;
            rig.minSize = 1.8f;
            // pivot on the ground plane where the view ray through the middle of all that meets it
            var c = rot * new Vector3((x0 + x1) / 2, (y0 + y1) / 2, Vector3.Dot(inv * b.center, Vector3.forward));
            var fwd = rot * Vector3.forward;
            float t = (rig.groundHeight - c.y) / fwd.y;
            homeCenter = c + fwd * t;
            if (frame) rig.Frame(homeCenter, homeSize);
        }

        /// <summary>Where the camera's pivot goes, and how much it shows, for this box to fill the view (times `margin`).</summary>
        (Vector3 center, float size) FrameOf(Bounds b, float margin)
        {
            var rot = Quaternion.Euler(rig.pitch, rig.yaw, 0);
            var inv = Quaternion.Inverse(rot);
            float w = 0, h = 0;
            for (int k = 0; k < 8; k++)
            {
                var corner = new Vector3((k & 1) == 0 ? b.min.x : b.max.x, (k & 2) == 0 ? b.min.y : b.max.y, (k & 4) == 0 ? b.min.z : b.max.z);
                var v = inv * (corner - b.center);
                w = Mathf.Max(w, Mathf.Abs(v.x));
                h = Mathf.Max(h, Mathf.Abs(v.y));
            }
            var fwd = rot * Vector3.forward;
            return (b.center + fwd * ((rig.groundHeight - b.center.y) / fwd.y), Mathf.Max(h, w / ((float)Screen.width / Screen.height)) * margin);
        }

        void BuildHud()
        {
            hud = UIKit.Canvas("HUD", 5);
            var root = hud.transform;
            var title = UIKit.Place(root, "Title", 32, 28, 330, 96);
            UIKit.Panel(title, UIKit.Paper);
            titleText = UIKit.Label(title, "初始·1桌", 40, UIKit.Ink, TextAnchor.MiddleCenter, FontStyle.Bold);
            var status = UIKit.Place(root, "Status", 32, 136, 330, 110);
            UIKit.Panel(status, new Color(UIKit.Paper.r, UIKit.Paper.g, UIKit.Paper.b, 0.92f));
            statusText = UIKit.Label(status, "", 28, UIKit.Ink, TextAnchor.MiddleLeft);
            var notice = UIKit.Rect(root, "Notice", new Vector2(0.5f, 1), new Vector2(0.5f, 1));
            notice.anchorMin = notice.anchorMax = new Vector2(0.5f, 0);
            notice.pivot = new Vector2(0.5f, 0);
            notice.anchoredPosition = new Vector2(0, 120);   // just above the hint bar, clear of the table bubble
            notice.sizeDelta = new Vector2(1200, 80);
            UIKit.Panel(notice, new Color(UIKit.Ink.r, UIKit.Ink.g, UIKit.Ink.b, 0.88f), false);
            noticeText = UIKit.Label(notice, "", 32, Color.white);
            notice.gameObject.SetActive(false);

            // business day: phase / time left, and the one button that moves the day on
            var day = UIKit.Rect(root, "Day", new Vector2(0.5f, 1), new Vector2(0.5f, 1));
            day.pivot = new Vector2(0.5f, 1);
            day.anchoredPosition = new Vector2(-150, -28);
            day.sizeDelta = new Vector2(640, 96);
            UIKit.Panel(day, UIKit.Paper);
            dayText = UIKit.Label(day, "", 32, UIKit.Ink);
            var dayBtn = UIKit.Rect(root, "DayButton", new Vector2(0.5f, 1), new Vector2(0.5f, 1));
            dayBtn.pivot = new Vector2(0, 1);
            dayBtn.anchoredPosition = new Vector2(170, -28);
            dayBtn.sizeDelta = new Vector2(260, 96);
            dayButton = UIKit.Button(dayBtn, "开门营业", 38, UIKit.Accent, Color.white, OnDayButton);
            dayButtonText = dayBtn.GetComponentInChildren<Text>();

            var home = UIKit.Rect(root, "Home", new Vector2(1, 1), new Vector2(1, 1));
            home.pivot = new Vector2(1, 1);
            home.anchoredPosition = new Vector2(-32, -28);
            home.sizeDelta = new Vector2(200, 96);
            UIKit.Button(home, "全景", 40, UIKit.Paper, UIKit.Ink, () => rig.Frame(homeCenter, homeSize));

            // 添置桌椅, under 全景: a dot on it when something can be bought this moment
            buyButton = UIKit.Rect(root, "Buy", new Vector2(1, 1), new Vector2(1, 1));
            buyButton.pivot = new Vector2(1, 1);
            buyButton.anchoredPosition = new Vector2(-32, -136);
            buyButton.sizeDelta = new Vector2(200, 96);
            UIKit.Button(buyButton, "添置", 40, UIKit.Paper, UIKit.Ink, OpenShopPanel);
            var dot = UIKit.Img(buyButton, "Dot", UIKit.Circle, UIKit.Fire, new Vector2(1, 1), new Vector2(1, 1));
            dot.rectTransform.sizeDelta = new Vector2(30, 30);
            dot.rectTransform.anchoredPosition = new Vector2(-10, -10);
            buyDot = dot.gameObject;

            var hint = UIKit.Rect(root, "Hint", new Vector2(0.5f, 0), new Vector2(0.5f, 0));
            hint.pivot = new Vector2(0.5f, 0);
            hint.anchoredPosition = new Vector2(0, 28);
            hint.sizeDelta = new Vector2(900, 76);
            UIKit.Panel(hint, new Color(UIKit.Paper.r, UIKit.Paper.g, UIKit.Paper.b, 0.9f));
            UIKit.Label(hint, "单指拖动·双指缩放·点「案台」进入做菜", 32, UIKit.InkSoft);

            // 打烊结算 panel
            settlement = UIKit.Rect(root, "Settlement", new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f));
            settlement.sizeDelta = new Vector2(1000, 820);
            UIKit.Panel(settlement, UIKit.Paper);
            var sTitle = UIKit.Rect(settlement, "Title", new Vector2(0, 1), new Vector2(1, 1), new Vector2(0, -110), new Vector2(0, -20));
            UIKit.Label(sTitle, "打烊结算", 52, UIKit.Ink, TextAnchor.MiddleCenter, FontStyle.Bold);
            var sBody = UIKit.Rect(settlement, "Body", Vector2.zero, Vector2.one, new Vector2(60, 150), new Vector2(-60, -120));
            settlementText = UIKit.Label(sBody, "", 34, UIKit.Ink, TextAnchor.UpperLeft);
            settlementText.lineSpacing = 1.3f;
            var next = UIKit.Rect(settlement, "Next", new Vector2(0.5f, 0), new Vector2(0.5f, 0));
            next.pivot = new Vector2(0.5f, 0);
            next.anchoredPosition = new Vector2(0, 40);
            next.sizeDelta = new Vector2(300, 90);
            UIKit.Button(next, "下一天", 40, UIKit.Accent, Color.white, NextDay);
            settlement.gameObject.SetActive(false);

            BuildShopPanel(root);
        }

        /// <summary>
        /// 下一天: an upgrade at the settlement opens it in the bigger shop, with one more block of the stove; a 二楼 built
        /// yesterday opens to guests. What is new is said once.
        /// </summary>
        void NextDay()
        {
            session.NextDay();
            ApplyStage();
            var p = session.Premises;
            var before = session.StageBefore;
            bool up = before != null && before != session.Stage;
            var stages = session.Data.Stages;
            int stoves = CookRules.StovesOpen(stages.IndexOf(session.Stage));
            var news = new List<string>();
            if (p.Expanded && p.ExpansionDay == session.Day.Day - 1) news.Add("二楼和雅间开张了，客人可以上楼了");
            if (up && stoves > CookRules.StovesOpen(stages.IndexOf(before))) news.Add($"灶台第 {stoves} 口锅开了");
            if (up && session.NextOffer is { Allowed: true } o && p.Next(before, session.Day.Day) is not { Allowed: true })
                news.Add($"可以添置{session.OfferName(o)}了（{o.Price / 100} 文）");
            if (news.Count > 0) Notice(string.Join("；", news));
        }

        // ------------------------------------------------------------------ 添置桌椅

        /// <summary>
        /// The 添置 page: what can be bought next (a table, or the 二楼 with 雅间一), its price, and why it can't be bought
        /// yet if it can't; under it every table of the shop by floor, those bought filled in.
        /// </summary>
        void BuildShopPanel(Transform root)
        {
            shopPanel = UIKit.Rect(root, "Shop", Vector2.zero, Vector2.one);
            var dim = UIKit.Rect(shopPanel, "Dim", Vector2.zero, Vector2.one);   // a tap beside the page closes it
            var dimImg = dim.gameObject.AddComponent<Image>();
            dimImg.color = new Color(0.16f, 0.1f, 0.05f, 0.35f);
            var dimBtn = dim.gameObject.AddComponent<Button>();
            dimBtn.transition = Selectable.Transition.None;
            dimBtn.onClick.AddListener(CloseShopPanel);

            var page = UIKit.Rect(shopPanel, "Page", new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f));
            page.sizeDelta = new Vector2(1120, 840);
            UIKit.Panel(page, UIKit.Paper);
            var title = UIKit.Rect(page, "Title", new Vector2(0, 1), new Vector2(1, 1), new Vector2(0, -104), new Vector2(0, -18));
            UIKit.Label(title, "添置桌椅", 52, UIKit.Ink, TextAnchor.MiddleCenter, FontStyle.Bold);
            var summary = UIKit.Rect(page, "Summary", new Vector2(0, 1), new Vector2(1, 1), new Vector2(50, -164), new Vector2(-50, -104));
            panelSummary = UIKit.Label(summary, "", 32, UIKit.InkSoft);

            // the next thing for sale: what it is on the left; its price, the button and what stands in the way on the right
            var card = UIKit.Rect(page, "Offer", new Vector2(0, 1), new Vector2(1, 1), new Vector2(50, -424), new Vector2(-50, -184));
            UIKit.Panel(card, UIKit.Card, false);
            offerName = UIKit.Label(UIKit.Rect(card, "Name", new Vector2(0, 0.62f), new Vector2(0.64f, 1), new Vector2(24, 0), new Vector2(0, -8)),
                                    "", 44, UIKit.Ink, TextAnchor.MiddleLeft, FontStyle.Bold);
            offerDetail = UIKit.Label(UIKit.Rect(card, "Detail", new Vector2(0, 0), new Vector2(0.64f, 0.62f), new Vector2(24, 14), new Vector2(0, 0)),
                                      "", 30, UIKit.InkSoft, TextAnchor.UpperLeft);
            offerDetail.lineSpacing = 1.15f;
            offerPrice = UIKit.Label(UIKit.Rect(card, "Price", new Vector2(0.64f, 0.66f), new Vector2(1, 1)), "", 46, UIKit.Ink, TextAnchor.MiddleCenter, FontStyle.Bold);
            var btn = UIKit.Rect(card, "Buy", new Vector2(0.68f, 0.26f), new Vector2(0.96f, 0.64f));
            offerButton = UIKit.Button(btn, "买下", 40, UIKit.Accent, Color.white, BuyNext);
            var cb = offerButton.colors;
            cb.disabledColor = Color.white;   // its colour is set by hand (grey when it can't be bought)
            offerButton.colors = cb;
            offerButtonText = btn.GetComponentInChildren<Text>();
            offerHint = UIKit.Label(UIKit.Rect(card, "Hint", new Vector2(0.62f, 0), new Vector2(1, 0.26f)), "", 28, UIKit.Fire);

            // every table of the shop, by floor: bought (green), for sale now (blue), the rest (grey)
            var rows = new[] { ("一楼", new[] { 1, 2, 3, 4 }), ("二楼", new[] { 5, 7, 8, 9, 10, 11 }), ("雅间", new[] { 6, 12 }) };
            for (int r = 0; r < rows.Length; r++)
            {
                float y = -452 - r * 82;
                var label = UIKit.Place(page, "Row" + r, 50, -y, 130, 66);
                UIKit.Label(label, rows[r].Item1, 34, UIKit.Ink, TextAnchor.MiddleLeft, FontStyle.Bold);
                var tables = rows[r].Item2;
                for (int i = 0; i < tables.Length; i++)
                {
                    var cell = UIKit.Place(page, $"Table{tables[i]}", 180 + i * 80, -y, 66, 66);
                    var img = UIKit.Panel(cell, UIKit.Locked, false);
                    mapCells.Add((tables[i], img, UIKit.Label(cell, tables[i].ToString(), 32, UIKit.InkSoft, TextAnchor.MiddleCenter, FontStyle.Bold)));
                }
                if (r == 1)
                    upstairsNote = UIKit.Label(UIKit.Place(page, "UpNote", 180 + tables.Length * 80 + 10, -y, 380, 66), "", 28, UIKit.InkSoft, TextAnchor.MiddleLeft);
            }

            var close = UIKit.Rect(page, "Close", new Vector2(0.5f, 0), new Vector2(0.5f, 0));
            close.pivot = new Vector2(0.5f, 0);
            close.anchoredPosition = new Vector2(0, 30);
            close.sizeDelta = new Vector2(240, 84);
            UIKit.Button(close, "关上", 36, UIKit.Paper, UIKit.Ink, CloseShopPanel);
            shopPanel.gameObject.SetActive(false);
        }

        void OpenShopPanel()
        {
            if (building || cooking.IsOpen || session.Day.Phase == DayPhase.Settlement) return;
            RefreshShopPanel();
            panelCash = session.Cash;
            shopPanel.gameObject.SetActive(true);
        }

        void CloseShopPanel() => shopPanel.gameObject.SetActive(false);

        void RefreshShopPanel()
        {
            var p = session.Premises;
            int day = session.Day.Day;
            var stage = session.Stage;
            var o = session.NextOffer;
            var open = p.OpenTables(day).ToList();
            panelSummary.text = $"钱 {session.Cash / 100} 文　·　现有 {open.Count} 张桌，「{StageShort(stage)}」最多 {stage.TableCap} 张";
            if (o == null)
            {
                bool soon = p.Expanded && !p.ExpansionOpen(day);
                offerName.text = soon ? "二楼和雅间修好了" : "桌椅都添齐了";
                offerDetail.text = soon ? "明天开张，客人就能上楼了。\n二楼再添桌，等开张以后。"
                                        : $"一楼 4 张，二楼 6 张，雅间 2 间，\n一共 {p.Bought.Count} 张桌。";
                offerPrice.text = offerHint.text = "";
                offerButton.gameObject.SetActive(false);
            }
            else
            {
                string where = p.Place(o.Table);
                offerName.text = o.Kind == OfferKind.Expansion ? "扩建二楼与雅间"
                               : where == "雅间二" ? "雅间二（第 12 张桌）" : $"第 {o.Table} 张桌（{where}）";
                offerDetail.text = o.Kind == OfferKind.Expansion ? "二楼散座和雅间一，各摆一张桌，连楼梯。\n今天修好，明天开张。"
                                 : where == "雅间二" ? "二楼的第二间雅间，配四把凳子。\n买下就摆好，马上能坐客人。"
                                 : $"摆在{(where == "一楼" ? "一楼大堂" : "二楼散座")}，配四把凳子。\n买下就摆好，马上能坐客人。";
                offerPrice.text = $"{o.Price / 100} 文";
                bool money = session.Cash >= o.Price;
                bool ok = o.Allowed && money && session.Day.Phase != DayPhase.Settlement;
                offerButton.gameObject.SetActive(true);
                offerButton.interactable = ok;
                offerButton.image.color = ok ? UIKit.Accent : UIKit.Locked;
                offerButtonText.text = o.Kind == OfferKind.Expansion ? "扩建" : "买下";
                offerButtonText.color = ok ? Color.white : UIKit.InkSoft;
                offerHint.text = !o.Allowed ? $"升到「{StageShort(o.NeedsStage)}」才能{(o.Kind == OfferKind.Expansion ? "扩建" : "添")}"
                               : !money ? $"还差 {(o.Price - session.Cash + 99) / 100} 文" : "";
                offerHint.color = o.Allowed ? UIKit.Fire : UIKit.InkSoft;
            }
            foreach (var (table, cell, label) in mapCells)
            {
                bool bought = p.Bought.Contains(table), seated = open.Contains(table);
                bool forSale = o is { Allowed: true } && o.Tables.Contains(table);
                cell.color = seated ? UIKit.Good : bought ? Color.Lerp(UIKit.Good, UIKit.Paper, 0.55f) : forSale ? UIKit.Accent : UIKit.Locked;
                label.color = seated || forSale ? Color.white : bought ? UIKit.Ink : UIKit.InkSoft;
            }
            var expansionStage = session.Data.Stages.FirstOrDefault(s => s.Id == session.Data.Premises.ExpansionMinStage);
            bool expansionLater = session.Data.Stages.IndexOf(stage) < session.Data.Stages.IndexOf(expansionStage);
            upstairsNote.text = p.Expanded ? (p.ExpansionOpen(day) ? "" : "明天开张")
                              : expansionLater ? $"「{StageShort(expansionStage)}」起可以扩建" : "一楼 4 张桌买齐后可以扩建";
            if (o is { Kind: OfferKind.Expansion }) upstairsNote.text = "";
        }

        static string StageShort(StageInfo s) => s == null ? "" : s.Name.Split(' ')[0];

        /// <summary>买下 on the 添置 page: pays and puts it in, the table popping into place or the 二楼 going up.</summary>
        void BuyNext()
        {
            var o = session.NextOffer;
            if (building || !session.Buy(o))
            {
                RefreshShopPanel();
                return;
            }
            CloseShopPanel();
            StartCoroutine(o.Kind == OfferKind.Expansion ? BuildExpansion(o) : PlaceTable(o));
        }

        /// <summary>A bought table pops into place, then the next one for sale (if any) shows as a sketch.</summary>
        IEnumerator PlaceTable(Offer o)
        {
            building = true;
            floor.Show(session.Premises, null, session.Day.Day);   // the bought one stands, no sketch meanwhile
            yield return floor.PopIn(o.Table);
            building = false;
            ShowFloor();
            FitRig(false);
            Notice($"{session.OfferName(o)}摆好了{(session.Day.Phase == DayPhase.Service ? "，马上能坐客人" : "")}");
        }

        /// <summary>The 二楼 goes up with the camera on it, then a sign over it says it opens tomorrow; back to the whole shop.</summary>
        IEnumerator BuildExpansion(Offer o)
        {
            building = true;
            rig.InputEnabled = false;
            var (center, size) = FrameOf(floor.ExpansionBounds(o.Tables), 1.25f);
            yield return Glide(center, Mathf.Clamp(size, rig.minSize, homeSize), 0.8f);
            yield return floor.Build(o.Tables);
            ShowFloor();
            Notice("二楼和雅间修好了，明天开张");
            yield return new WaitForSecondsRealtime(1.2f);
            FitRig(false);
            yield return Glide(homeCenter, homeSize, 0.9f);
            rig.InputEnabled = true;
            building = false;
        }

        void OnDayButton()
        {
            var day = session.Day;
            if (day.Phase == DayPhase.BeforeOpening) session.OpenShop();
            else if (day.Phase == DayPhase.Service)
            {
                if (session.CanCloseEarly) session.CloseShop();
                else Notice("还有客人在店里，招待完才能打烊");
            }
        }

        void Notice(string msg) => Notice(null, msg);

        void Notice(Party party, string msg)
        {
            if (msg.Contains("没有空桌") && session.CanBuyNow) msg += "（点「添置」加桌）";
            noticeText.text = msg;
            noticeText.transform.parent.gameObject.SetActive(true);
            noticeUntil = Time.time + 3f;
            if (party != null && msg.Contains("结账"))   // the bill over the table that paid: 结账 N 文
            {
                var bill = msg.Substring(msg.IndexOf("结账"));
                int cut = bill.IndexOf(" · ");
                guests.Flash(party.Table, cut > 0 ? bill.Substring(0, cut) : bill);
            }
        }

        void Update()
        {
            if (session == null) return;
            long now = GameSession.NowMs;
            var day = session.Day;
            session.Tick();
            session.TickKitchen();
            guests.Sync(session.Service, now);
            if (noticeText.transform.parent.gameObject.activeSelf && Time.time > noticeUntil)
                noticeText.transform.parent.gameObject.SetActive(false);
            var stage = session.Stage;
            var next = session.Data.NextStage(session.Xp);
            titleText.text = stage.Name.Split(' ')[0];
            statusText.text = $"钱 {session.Cash / 100} 文\n经验 {session.Xp}{(next != null ? $" / {next.Xp}" : "")}";
            switch (day.Phase)
            {
                case DayPhase.BeforeOpening:
                    dayText.text = $"第 {day.Day} 天·开门前";
                    dayButtonText.text = "开门营业";
                    break;
                case DayPhase.Service:
                    long left = day.RemainingMs(now);
                    var sv = session.Service;
                    dayText.text = left > 0
                        ? $"第 {day.Day} 天·营业 {left / 60000}:{left / 1000 % 60:00}·来客 {sv.GuestsArrived}/{sv.Planned}"
                        : $"第 {day.Day} 天·已关门，招待完在座客人";
                    dayButtonText.text = "提前打烊";
                    break;
                case DayPhase.Settlement:
                    dayText.text = $"第 {day.Day} 天·打烊结算";
                    break;
            }
            bool settling = day.Phase == DayPhase.Settlement;
            dayButton.gameObject.SetActive(!settling);
            var offer = session.NextOffer;
            bool affordable = offer != null && session.Cash >= offer.Price;
            buyButton.gameObject.SetActive(!settling && !building);
            buyDot.SetActive(offer is { Allowed: true } && affordable);
            floor.SetAffordable(affordable);
            if (shopPanel.gameObject.activeSelf)
            {
                if (settling || building) CloseShopPanel();
                else if (session.Cash != panelCash) { panelCash = session.Cash; RefreshShopPanel(); }   // a bill came in
            }
            if (settling && !settlement.gameObject.activeSelf) settlementText.text = SettlementText();
            settlement.gameObject.SetActive(settling);
            if (settling) noticeText.transform.parent.gameObject.SetActive(false);

            station?.SetAlert(session.AnyStoveCooking() ? "锅里有菜！" : session.AnyWokDone ? "可以装盘" :
                              session.AnyTrayWaiting ? "有菜待端" : null);
        }

        string SettlementText()
        {
            var day = session.Day;
            var sv = session.Service;
            int Get(Quality q) => day.Served.TryGetValue(q, out var n) ? n : 0;
            var lines = new List<string>
            {
                $"第 {day.Day} 天{(day.ClosedEarly ? "（提前打烊）" : "")}　来客 {sv.GuestsArrived} 人，结账 {sv.GuestsPaid} 人{(sv.GuestsLeft > 0 ? $"，走了 {sv.GuestsLeft} 人" : "")}",
                $"好评 {sv.Good}　一般 {sv.Normal}　差评 {sv.Bad}",
                $"出菜：完美 {Get(Quality.Perfect)}　没熟 {Get(Quality.Underdone)}　糊了 {Get(Quality.Burnt)}{(sv.Wasted > 0 ? $"　倒掉 {sv.Wasted}" : "")}",
                $"收入 {sv.Revenue / 100} 文　经验 +{sv.Xp}（共 {session.Xp}）",
                $"明天口碑系数 {session.Reputation:0.00}",
            };
            if (session.BoughtToday.Count > 0)
                lines.Add("今天添置：" + string.Join("、", session.BoughtToday.Select(b => $"{b.what} {b.price / 100} 文")));
            if (session.Premises.ExpansionDay == day.Day) lines.Add("二楼和雅间明天开张");
            if (session.Stage != session.StageBefore)
            {
                lines.Add($"升到「{session.Stage.Name}」！");
                var stages = session.Data.Stages;
                int stoves = CookRules.StovesOpen(stages.IndexOf(session.Stage));
                if (stoves > CookRules.StovesOpen(stages.IndexOf(session.StageBefore))) lines.Add($"明天灶台多开一口锅（共 {stoves} 口）");
                if (session.Premises.Next(session.Stage, day.Day + 1) is { Allowed: true } o &&
                    session.Premises.Next(session.StageBefore, day.Day + 1) is not { Allowed: true })
                    lines.Add($"明天可以添置{session.OfferName(o)}（{o.Price / 100} 文）");
            }
            if (session.NewlyOpened.Count > 0) lines.Add("新菜：" + string.Join("、", session.NewlyOpened.Select(r => r.Name)));
            if (day.Day % 10 == 0) lines.Add("今天发工钱");
            return string.Join("\n", lines);
        }

        void OnTap(Vector2 screen)
        {
            if (cooking.IsOpen || building || session.Day.Phase == DayPhase.Settlement) return;
            var ray = rig.Cam.ScreenPointToRay(screen);
            if (Physics.Raycast(ray, out var hit, 500f) && station && hit.collider.GetComponentInParent<CookStation>() == station)
                StartCoroutine(OpenCooking());
            else if (floor.HitSale(screen))   // the table (or the 二楼) for sale, or its price tag
                OpenShopPanel();
        }

        IEnumerator OpenCooking()
        {
            rig.InputEnabled = false;
            station.Flash();
            yield return new WaitForSecondsRealtime(0.18f);
            hud.gameObject.SetActive(false);
            station.ShowTag(false);
            rig.Cam.enabled = false;           // the cooking screen has its own camera on the counter set
            cooking.Open();
        }

        void OnCookingClosed()
        {
            rig.Cam.enabled = true;
            hud.gameObject.SetActive(true);
            station.ShowTag(true);
            rig.InputEnabled = true;
        }

        static Transform FindDeep(Transform t, string name)
        {
            if (t.name == name) return t;
            foreach (Transform c in t)
            {
                var f = FindDeep(c, name);
                if (f) return f;
            }
            return null;
        }

        // ------------------------------------------------------------------ the demo video

        /// <summary>The camera eased from where it is to a new centre and size over `seconds`.</summary>
        IEnumerator Glide(Vector3 center, float size, float seconds)
        {
            Vector3 c0 = rig.Pivot;
            float s0 = rig.Cam.orthographicSize;
            for (float t = 0; t < seconds; t += Time.unscaledDeltaTime)
            {
                float e = Mathf.SmoothStep(0f, 1f, t / seconds);
                rig.Frame(Vector3.Lerp(c0, center, e), Mathf.Lerp(s0, size, e));
                yield return null;
            }
            rig.Frame(center, size);
        }

        /// <summary>
        /// Run a player with  -video  to play the demo by itself for a screen recording (about a minute and a half),
        /// then quit: the shop opens and the first table orders; in the kitchen each ordered dish is cooked the
        /// player's way (its raw ingredients tapped into the wok one by one, tossed, 出锅 in the gold, 装盘 to a
        /// tray) and carried out; the table eating in the hall; then back in the kitchen a run of the other dishes
        /// (raw ingredients tossed, 出锅 in the gold, the finished dish in the wok, plated onto the trays); and the
        /// whole shop again.
        /// </summary>
        IEnumerator PlayForVideo()
        {
            var table = FindDeep(level, "D_Table_1");
            var atTable = table.position + new Vector3(-0.5f, 0, -0.8f);
            yield return new WaitForSecondsRealtime(3.0f);              // the whole shop
            OnDayButton();                                              // 开门营业
            yield return Glide(atTable, 3.2f, 2.5f);
            yield return new WaitForSecondsRealtime(4.0f);              // the guests come in and sit down
            yield return OpenCooking();
            yield return new WaitForSecondsRealtime(1.5f);
            // the orders, cooked the player's way and carried out
            while (cooking.DemoSelectPending() != null)
            {
                yield return new WaitForSecondsRealtime(0.6f);
                foreach (var id in cooking.DemoNeeds())
                {
                    cooking.DemoTap(id);                                // dropped into the wok
                    yield return new WaitForSecondsRealtime(0.35f);
                }
                yield return new WaitForSecondsRealtime(1.8f);          // tossed about
                while (!cooking.NeedleInGold()) yield return null;
                cooking.DemoTakeOut();                                  // 出锅: the finished dish in the wok
                yield return new WaitForSecondsRealtime(1.3f);
                cooking.DemoPlate();                                    // 装盘
                yield return new WaitForSecondsRealtime(1.0f);
                cooking.DemoServeAll();                                 // carried to the table
                yield return new WaitForSecondsRealtime(0.4f);
            }
            // the table eating, their dishes in front of them, and close up on the table
            yield return new WaitForSecondsRealtime(1.0f);
            cooking.Close();
            rig.Frame(atTable, 3.2f);
            yield return new WaitForSecondsRealtime(0.8f);
            float minSize = rig.minSize;
            rig.minSize = 0.5f;
            // the pivot moved back along the view so that the table top (0.78 m up) sits in the middle of it
            var f = rig.Cam.transform.forward;
            var fh = new Vector3(f.x, 0, f.z);
            float tanPitch = -f.y / Mathf.Max(fh.magnitude, 1e-4f);
            var tableTop = table.position + fh.normalized * (0.78f / Mathf.Max(tanPitch, 0.1f));
            yield return Glide(tableTop, 0.62f, 3.0f);
            yield return new WaitForSecondsRealtime(3.5f);
            yield return Glide(table.position + new Vector3(-0.2f, 0, -0.3f), 2.3f, 2.0f);
            rig.minSize = minSize;
            // back in the kitchen, the other dishes: raw ingredients tossed, 出锅 in the gold, plated; now and then
            // close up on the wok (raw → the finished dish) and on the trays (the plated dishes)
            yield return OpenCooking();
            cooking.DemoQuiet = true;
            yield return new WaitForSecondsRealtime(1.0f);
            var dishes = new[] { "D10", "D07", "D19", "D18", "D12", "D14", "D15", "D13", "D22" };
            for (int k = 0; k < dishes.Length; k++)
            {
                bool closeUp = k % 3 == 1;                              // the middle dish of each three, in the wok
                cooking.DemoShowcase(dishes[k]);
                if (closeUp) yield return cooking.DemoCloseUp(cooking.DemoWok + Vector3.up * 0.05f, 1.35f, 1.2f);
                yield return new WaitForSecondsRealtime(closeUp ? 2.2f : 2.0f);   // tossed about
                while (!cooking.NeedleInGold()) yield return null;
                cooking.DemoTakeOut();
                yield return new WaitForSecondsRealtime(closeUp ? 2.0f : 1.4f);
                if (closeUp) yield return cooking.DemoCloseUp(Vector3.zero, 0f, 1.0f);
                cooking.DemoPlate();
                yield return new WaitForSecondsRealtime(1.0f);
                if (cooking.DemoTraysFull())                            // three plated: close up on them
                {
                    yield return cooking.DemoCloseUp(cooking.DemoTrays + Vector3.up * 0.06f, 1.45f, 1.4f);
                    yield return new WaitForSecondsRealtime(3.0f);
                    yield return cooking.DemoCloseUp(Vector3.zero, 0f, 1.2f);
                    cooking.DemoClearTrays();
                    yield return new WaitForSecondsRealtime(0.4f);
                }
            }
            yield return new WaitForSecondsRealtime(1.0f);
            cooking.DemoClearTrays();
            cooking.Close();                                            // the whole shop again
            rig.Frame(table.position + new Vector3(-0.2f, 0, -0.3f), 2.3f);
            yield return Glide(homeCenter, homeSize, 3.0f);
            yield return new WaitForSecondsRealtime(2.0f);
            Application.Quit();
        }

        // ------------------------------------------------------------------ automated screenshots

        /// <summary>
        /// Run a player with  -wok &lt;dir&gt; [D08,D07,…]  to look at the raw pieces in the wok: each listed dish is cooked
        /// at once (its raw ingredients straight in) and seen close up while they are tossed, a picture every 0.17 s
        /// for a toss and a half (wok_&lt;dish&gt;_&lt;k&gt;.png), then the finished dish in the wok (wok_&lt;dish&gt;_done.png);
        /// then it quits.
        /// </summary>
        IEnumerator WokShots(string dir, string dishes)
        {
            Directory.CreateDirectory(dir);
            yield return new WaitForSecondsRealtime(1.0f);
            yield return OpenCooking();
            cooking.DemoQuiet = true;
            yield return new WaitForSecondsRealtime(0.8f);
            foreach (var id in dishes.Split(','))
            {
                cooking.DemoShowcase(id);
                yield return cooking.DemoCloseUp(cooking.DemoWok + Vector3.up * 0.05f, 1.0f, 0.6f);
                yield return new WaitForSecondsRealtime(0.6f);
                for (int k = 0; k < 8; k++)
                {
                    yield return new WaitForEndOfFrame();
                    ScreenCapture.CaptureScreenshot(Path.Combine(dir, $"wok_{id}_{k}.png"));
                    yield return new WaitForSecondsRealtime(0.17f);
                }
                while (!cooking.NeedleInGold()) yield return null;
                cooking.DemoTakeOut();
                yield return new WaitForSecondsRealtime(1.0f);
                yield return new WaitForEndOfFrame();
                ScreenCapture.CaptureScreenshot(Path.Combine(dir, $"wok_{id}_done.png"));
                yield return new WaitForSecondsRealtime(0.4f);
                cooking.DemoPlate();
                yield return new WaitForSecondsRealtime(1.2f);
                cooking.DemoClearTrays();
                yield return cooking.DemoCloseUp(Vector3.zero, 0f, 0.3f);
            }
            Application.Quit();
        }

        /// <summary>
        /// -shopshot: the shop of the stage it was started at (-stage), photographed empty, then with a party at every
        /// table (every other table served, its dishes on the table; the rest waiting), whole and close on the tables:
        /// shop_&lt;stage&gt;_empty / shop_&lt;stage&gt; / shop_&lt;stage&gt;_tables.png. Then it quits.
        /// </summary>
        IEnumerator ShopShot(string dir)
        {
            Directory.CreateDirectory(dir);
            string id = session.Stage.Id;
            IEnumerator Shot(string name)
            {
                yield return new WaitForEndOfFrame();
                ScreenCapture.CaptureScreenshot(Path.Combine(dir, name + ".png"));
                yield return new WaitForSecondsRealtime(0.4f);
            }
            yield return new WaitForSecondsRealtime(1.5f);
            yield return Shot($"shop_{id}_empty");
            OnDayButton();                                      // 开门营业
            for (int k = 0; k < session.Service.Tables.Count; k++) session.Service.ArriveNow(GameSession.NowMs);
            yield return new WaitForSecondsRealtime(0.6f);      // seated, orders taken
            foreach (var p in session.Service.Parties.Where(p => p.State == PartyState.Waiting && p.Table % 2 == 0).ToList())
                foreach (var pl in p.Plates.Where(x => !x.Served).ToList())
                    session.Service.Serve(p, pl, Quality.Perfect, GameSession.NowMs);
            yield return new WaitForSecondsRealtime(1.0f);
            yield return Shot($"shop_{id}");
            // close on the tables
            var b = new Bounds();
            bool any = false;
            foreach (var t in level.GetComponentsInChildren<Transform>().Where(x => x.name.StartsWith("D_Table_")))
                foreach (var r in t.GetComponentsInChildren<Renderer>())
                {
                    if (!any) { b = r.bounds; any = true; }
                    else b.Encapsulate(r.bounds);
                }
            if (any)
            {
                b.Expand(new Vector3(2.4f, 4.0f, 2.4f));   // the stools round the tables, and the bubbles over them
                var (center, size) = FrameOf(b, 1f);
                float minSize = rig.minSize;
                rig.minSize = 0.5f;
                rig.Frame(center, size);
                yield return new WaitForSecondsRealtime(0.5f);
                yield return Shot($"shop_{id}_tables");
                rig.minSize = minSize;
            }
            Application.Quit();
        }

        /// <summary>
        /// -buyshots: buying the next thing for sale, photographed (buy_&lt;stage&gt;_…): the shop with it standing as a sketch
        /// under its price (1_sale), the 添置 page (2_page), then a table popping into place (3_pop, 4_bought), or the 二楼
        /// going up (3_build_a…c, 4_built with its sign), the day's settlement (5_settle), the next morning with the 二楼
        /// open (6_next_day) and a party at every table, upstairs too (7_guests). Then it quits.
        /// </summary>
        IEnumerator BuyShots(string dir)
        {
            Directory.CreateDirectory(dir);
            string id = session.Stage.Id;
            IEnumerator Shot(string name)
            {
                yield return new WaitForEndOfFrame();
                ScreenCapture.CaptureScreenshot(Path.Combine(dir, $"buy_{id}_{name}.png"));
                yield return new WaitForSecondsRealtime(0.2f);
            }
            yield return new WaitForSecondsRealtime(1.5f);
            yield return Shot("1_sale");
            OpenShopPanel();
            yield return new WaitForSecondsRealtime(0.3f);
            yield return Shot("2_page");
            var o = session.NextOffer;
            if (o is not { Allowed: true } || session.Cash < o.Price)
            {
                Debug.LogError("BuyShots: nothing can be bought now");
                Application.Quit();
                yield break;
            }
            BuyNext();
            if (o.Kind == OfferKind.Table)
            {
                yield return new WaitForSecondsRealtime(0.22f);
                yield return Shot("3_pop");
                while (building) yield return null;
                yield return new WaitForSecondsRealtime(0.5f);
                yield return Shot("4_bought");
                Application.Quit();
                yield break;
            }
            foreach (var (wait, name) in new[] { (1.5f, "3_build_a"), (0.7f, "3_build_b"), (0.9f, "3_build_c") })
            {
                yield return new WaitForSecondsRealtime(wait);
                yield return Shot(name);
            }
            while (building) yield return null;
            yield return new WaitForSecondsRealtime(0.3f);
            yield return Shot("4_built");
            OnDayButton();                                      // 开门营业, and 提前打烊 at once: the day's settlement
            session.CloseShop();
            yield return new WaitForSecondsRealtime(0.5f);
            yield return Shot("5_settle");
            NextDay();
            yield return new WaitForSecondsRealtime(0.6f);
            yield return Shot("6_next_day");
            OnDayButton();
            for (int k = 0; k < session.Service.Tables.Count; k++) session.Service.ArriveNow(GameSession.NowMs);
            yield return new WaitForSecondsRealtime(0.6f);
            foreach (var p in session.Service.Parties.Where(p => p.State == PartyState.Waiting && p.Table % 2 == 0).ToList())
                foreach (var pl in p.Plates.Where(x => !x.Served).ToList())
                    session.Service.Serve(p, pl, Quality.Perfect, GameSession.NowMs);
            yield return new WaitForSecondsRealtime(1.0f);
            yield return Shot("7_guests");
            Application.Quit();
        }

        /// <summary>
        /// -stoveshots: the cooking screen at the stage it was started at (-stage), photographed (stove_&lt;stage&gt;_…): the
        /// stove with the blocks that stage has open, the rest with their lids on (1_open); a dish cooking in every open wok
        /// (2_cooking); the first one out and waiting for 装盘 while the others cook (3_out); the second wok picked (4_picked).
        /// Then it quits.
        /// </summary>
        IEnumerator StoveShots(string dir)
        {
            Directory.CreateDirectory(dir);
            string id = session.Stage.Id;
            IEnumerator Shot(string name)
            {
                yield return new WaitForEndOfFrame();
                ScreenCapture.CaptureScreenshot(Path.Combine(dir, $"stove_{id}_{name}.png"));
                yield return new WaitForSecondsRealtime(0.25f);
            }
            yield return new WaitForSecondsRealtime(1.2f);
            yield return OpenCooking();
            cooking.DemoQuiet = true;
            cooking.DemoChoose("D01");
            yield return new WaitForSecondsRealtime(0.8f);
            yield return Shot("1_open");
            var dishes = new[] { "D01", "D02", "D03", "D10" };
            int open = Mathf.Min(session.Stoves.Count(x => x.Unlocked), cooking.DemoBlocks);
            for (int k = open - 1; k >= 0; k--)   // the first wok last, so that it is the picked one
            {
                cooking.DemoCookOn(k, dishes[k % dishes.Length]);
                yield return new WaitForSecondsRealtime(0.4f);
            }
            yield return new WaitForSecondsRealtime(0.8f);
            yield return Shot("2_cooking");
            while (!cooking.NeedleInGold()) yield return null;
            cooking.DemoTakeOut();                                  // the first wok: out, waiting for 装盘
            yield return new WaitForSecondsRealtime(0.8f);
            yield return Shot("3_out");
            if (open > 1)
            {
                cooking.DemoCookOn(1);
                yield return new WaitForSecondsRealtime(0.4f);
                yield return Shot("4_picked");
            }
            Application.Quit();
        }

        IEnumerator TakeShots(string dir)
        {
            Directory.CreateDirectory(dir);
            IEnumerator Shot(string name)
            {
                yield return new WaitForEndOfFrame();
                ScreenCapture.CaptureScreenshot(Path.Combine(dir, name + ".png"));
                yield return new WaitForSecondsRealtime(0.4f);
            }

            yield return new WaitForSecondsRealtime(1.5f);
            yield return Shot("1_overview");
            OnDayButton();                                    // 开门营业: the first group comes in ~4 s
            var table = FindDeep(level, "D_Table_1");
            rig.Frame(table.position + new Vector3(-0.5f, 0, -0.8f), 3.2f);
            yield return new WaitForSecondsRealtime(5f);
            yield return Shot("2_guests_seated");
            var sp = rig.Cam.WorldToScreenPoint(station.GetComponent<BoxCollider>().bounds.center);
            OnTap(sp);
            yield return new WaitForSecondsRealtime(0.6f);
            yield return Shot("3_cooking_orders");
            int n = 0;
            while (cooking.DemoCookPending())
            {
                yield return new WaitForSecondsRealtime(1.0f);
                while (cooking.NeedleInGold()) yield return null;   // wait for the next pass through the gold
                if (n == 0) yield return Shot("4_cooking");
                if (n == 0) yield return Shot("4b_cooking");   // the raw ingredients a moment later, mid-toss
                while (!cooking.NeedleInGold()) yield return null;
                cooking.DemoTakeOut();
                yield return new WaitForSecondsRealtime(0.6f);
                if (n == 0) yield return Shot("5_out_of_the_wok");    // the finished dish in the wok
                cooking.DemoPlate();
                yield return new WaitForSecondsRealtime(0.25f);
                if (n == 0) yield return Shot("5a_plating");           // flying to its tray
                yield return new WaitForSecondsRealtime(0.5f);
                if (n == 0) yield return Shot("5b_plated");
                cooking.DemoServeAll();
                yield return new WaitForSecondsRealtime(0.2f);
                n++;
            }
            yield return Shot("5b_all_served");
            cooking.Close();
            yield return new WaitForSecondsRealtime(1f);
            yield return Shot("6_hall_dining");
            float until = Time.realtimeSinceStartup + 40f;   // the next group may walk in meanwhile
            while (!session.Service.Parties.Where(p => p.Table == 0).All(p => p.State != PartyState.Dining && p.State != PartyState.Waiting) && Time.realtimeSinceStartup < until) yield return null;
            yield return new WaitForSecondsRealtime(0.3f);
            yield return Shot("7_checkout");
            OnDayButton();                                    // 提前打烊 now that the table has paid
            yield return new WaitForSecondsRealtime(0.5f);
            yield return Shot("8_settlement");
            Application.Quit();
        }
    }
}
