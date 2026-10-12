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
    /// The shop grows with the 声望 stage: shops[0] is 初始·1桌, shops[1…5] the shop at 一级 … 五级 (build_shop.py), each
    /// with as many of its tables as the stage allows; the day after an upgrade opens in the new shop.
    ///
    /// Run a player with  -shots &lt;folder&gt;  to save the demo screenshots there and quit;  -stage &lt;id&gt;  (1_1, 1_2, 1_3, 2 … 5)
    /// starts at that stage;  -shopshot &lt;folder&gt;  photographs that stage's shop with every table taken, then quits.
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

        void Start()
        {
            Application.targetFrameRate = 60;
            if (EventSystem.current == null)
                new GameObject("EventSystem", typeof(EventSystem), typeof(InputSystemUIInputModule));

            session = new GameSession();
            var args = System.Environment.GetCommandLineArgs();
            int si = System.Array.IndexOf(args, "-stage");
            if (si >= 0 && si + 1 < args.Length)
            {
                var stage = session.Data.Stages.FirstOrDefault(x => x.Id == args[si + 1]);
                if (stage != null) session.Xp = stage.Xp;
                else Debug.LogError($"GameFlow: no stage '{args[si + 1]}'");
            }
            if (shops == null || shops.Length == 0) shops = new[] { level };

            guests = new GameObject("Guests").AddComponent<GuestViews>();
            session.Service.Notice += Notice;

            cooking = new GameObject("Cooking").AddComponent<CookingScreen>();
            cooking.Build(session, cookSet);
            cooking.Closed += OnCookingClosed;

            rig.Tapped += OnTap;
            sceneMask = rig.Cam.cullingMask;
            ApplyStage();
            BuildHud();

            int i = System.Array.IndexOf(args, "-shots");
            if (i >= 0 && i + 1 < args.Length) StartCoroutine(TakeShots(args[i + 1]));
            int ss = System.Array.IndexOf(args, "-shopshot");
            if (ss >= 0 && ss + 1 < args.Length) StartCoroutine(ShopShot(args[ss + 1]));
            if (System.Array.IndexOf(args, "-video") >= 0) StartCoroutine(PlayForVideo());
            int w = System.Array.IndexOf(args, "-wok");
            if (w >= 0 && w + 1 < args.Length)
                StartCoroutine(WokShots(args[w + 1], w + 2 < args.Length && !args[w + 2].StartsWith("-") ? args[w + 2] : "D08"));
        }

        /// <summary>Which shop a stage keeps: 初始·1桌 for 一级①, the 一级 shop for ②③, then one per level.</summary>
        static int ShopFor(StageInfo s) => s.Id switch { "1_1" => 0, "1_2" or "1_3" => 1, "2" => 2, "3" => 3, "4" => 4, "5" => 5, _ => 0 };

        /// <summary>The shop for the current stage on show, with as many tables as the stage allows (until tables are
        /// bought one by one, a stage comes with all of them).</summary>
        void ApplyStage()
        {
            UseShop(ShopFor(session.Stage));
            session.TablesInShop = Mathf.Max(1, Mathf.Min(session.Stage.TableCap, guests.TableCount));
            guests.ShowTables(session.TablesInShop);
        }

        void UseShop(int idx)
        {
            idx = Mathf.Clamp(idx, 0, shops.Length - 1);
            while (idx > 0 && shops[idx] == null) idx--;
            if (idx == shopIndex) return;
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
            guests.Setup(level, rig.Cam);
            FitRig();
        }

        /// <summary>Clamp and zoom limits from the level's bounds, then show the whole shop.</summary>
        void FitRig()
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
            rig.Frame(homeCenter, homeSize);
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
            notice.sizeDelta = new Vector2(820, 80);
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

            var hint = UIKit.Rect(root, "Hint", new Vector2(0.5f, 0), new Vector2(0.5f, 0));
            hint.pivot = new Vector2(0.5f, 0);
            hint.anchoredPosition = new Vector2(0, 28);
            hint.sizeDelta = new Vector2(900, 76);
            UIKit.Panel(hint, new Color(UIKit.Paper.r, UIKit.Paper.g, UIKit.Paper.b, 0.9f));
            UIKit.Label(hint, "单指拖动·双指缩放·点「案台」进入做菜", 32, UIKit.InkSoft);

            // 打烊结算 panel
            settlement = UIKit.Rect(root, "Settlement", new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f));
            settlement.sizeDelta = new Vector2(1000, 700);
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
            UIKit.Button(next, "下一天", 40, UIKit.Accent, Color.white, () =>
            {
                session.Day.NextDay();
                ApplyStage();   // an upgrade opens the next day in the bigger shop
            });
            settlement.gameObject.SetActive(false);
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
            if (session.Stage != session.StageBefore) lines.Add($"升到「{session.Stage.Name}」！");
            if (session.NewlyOpened.Count > 0) lines.Add("新菜：" + string.Join("、", session.NewlyOpened.Select(r => r.Name)));
            if (day.Day % 10 == 0) lines.Add("今天发工钱");
            return string.Join("\n", lines);
        }

        void OnTap(Vector2 screen)
        {
            if (cooking.IsOpen || session.Day.Phase == DayPhase.Settlement) return;
            var ray = rig.Cam.ScreenPointToRay(screen);
            if (Physics.Raycast(ray, out var hit, 500f) && station && hit.collider.GetComponentInParent<CookStation>() == station)
                StartCoroutine(OpenCooking());
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
            for (int k = 0; k < session.TablesInShop; k++) session.Service.ArriveNow(GameSession.NowMs);
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
                float minSize = rig.minSize;
                rig.minSize = 0.5f;
                rig.Frame(b.center + fwd * ((rig.groundHeight - b.center.y) / fwd.y), Mathf.Max(h, w / ((float)Screen.width / Screen.height)));
                yield return new WaitForSecondsRealtime(0.5f);
                yield return Shot($"shop_{id}_tables");
                rig.minSize = minSize;
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
