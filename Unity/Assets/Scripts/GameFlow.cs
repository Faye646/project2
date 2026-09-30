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
    /// Run a player with  -shots &lt;folder&gt;  to save the demo screenshots there and quit.
    /// </summary>
    public class GameFlow : MonoBehaviour
    {
        public CameraRig rig;
        public Transform level;
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

        void Start()
        {
            Application.targetFrameRate = 60;
            if (EventSystem.current == null)
                new GameObject("EventSystem", typeof(EventSystem), typeof(InputSystemUIInputModule));

            session = new GameSession();

            var st = FindDeep(level, stationName);
            if (st != null)
            {
                station = st.gameObject.AddComponent<CookStation>();
                station.Setup(rig.Cam);
            }
            else Debug.LogError($"GameFlow: no '{stationName}' under {level.name}");

            guests = new GameObject("Guests").AddComponent<GuestViews>();
            guests.Setup(level, rig.Cam);
            session.Service.Notice += (party, msg) => Notice(msg);

            cooking = new GameObject("Cooking").AddComponent<CookingScreen>();
            cooking.Build(session, cookSet);
            cooking.Closed += OnCookingClosed;

            rig.Tapped += OnTap;
            sceneMask = rig.Cam.cullingMask;
            FitRig();
            BuildHud();

            var args = System.Environment.GetCommandLineArgs();
            int i = System.Array.IndexOf(args, "-shots");
            if (i >= 0 && i + 1 < args.Length) StartCoroutine(TakeShots(args[i + 1]));
        }

        /// <summary>Clamp and zoom limits from the level's bounds, then show the whole shop.</summary>
        void FitRig()
        {
            var b = new Bounds(level.position, Vector3.zero);
            foreach (var r in level.GetComponentsInChildren<Renderer>()) b.Encapsulate(r.bounds);
            rig.bounds = new Rect(b.min.x, b.min.z, b.size.x, b.size.z);

            // size that fits all eight corners of the bounds in view
            var rot = Quaternion.Euler(rig.pitch, rig.yaw, 0);
            var inv = Quaternion.Inverse(rot);
            float w = 0, h = 0;
            var c = b.center;
            for (int k = 0; k < 8; k++)
            {
                var corner = new Vector3((k & 1) == 0 ? b.min.x : b.max.x, (k & 2) == 0 ? b.min.y : b.max.y, (k & 4) == 0 ? b.min.z : b.max.z);
                var v = inv * (corner - c);
                w = Mathf.Max(w, Mathf.Abs(v.x));
                h = Mathf.Max(h, Mathf.Abs(v.y));
            }
            float aspect = (float)Screen.width / Screen.height;
            homeSize = Mathf.Max(h, w / aspect) * 1.06f;
            rig.maxSize = homeSize * 1.15f;
            rig.minSize = 1.8f;
            // pivot on the ground plane under the bounds' centre, along the view ray
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
            UIKit.Button(next, "下一天", 40, UIKit.Accent, Color.white, () => session.Day.NextDay());
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

        void Notice(string msg)
        {
            noticeText.text = msg;
            noticeText.transform.parent.gameObject.SetActive(true);
            noticeUntil = Time.time + 3f;
            if (msg.Contains("结账")) guests.Flash(msg.Substring(msg.IndexOf("结账")));
        }

        void Update()
        {
            if (session == null) return;
            long now = GameSession.NowMs;
            var day = session.Day;
            session.Tick();
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

            station?.SetAlert(session.AnyStoveCooking() ? "锅里有菜！" : session.AnyTrayWaiting ? "有菜待端" : null);
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

        // ------------------------------------------------------------------ automated screenshots

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
                while (!cooking.NeedleInGold()) yield return null;
                cooking.DemoTakeOut();
                yield return new WaitForSecondsRealtime(0.3f);
                if (n == 0) yield return Shot("5_out_of_the_wok");
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
