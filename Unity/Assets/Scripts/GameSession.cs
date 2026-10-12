using System.Collections.Generic;
using System.Linq;
using BianHe.Core;
using UnityEngine;

namespace BianHe
{
    /// <summary>
    /// Everything that outlives a screen: design data, stoves (they keep cooking while the player is
    /// back in the hall), the 放置区 trays, the guests of the day, money, experience, 自动做菜
    /// counters, the tables bought, the business day and first-time achievements.
    /// </summary>
    public class GameSession
    {
        public const int TrayCount = 3;

        public readonly GameData Data;
        public readonly CookBook Book = new() { Counting = false };   // 初始·1桌 is 第一关: nothing counts yet
        public readonly BusinessDay Day = new();
        public readonly Service Service;
        public readonly Premises Premises;                               // the tables bought and the 二楼
        public readonly List<Stove> Stoves = new();                      // the stove's four blocks, open by 声望 (OpenStoves)
        public readonly HashSet<string> Achievements = new();
        public readonly HashSet<string> Flags = new();
        public int Xp;
        public int Cash;                                                 // 1/100 文
        public double Reputation = 1.0;                                  // 口碑系数; day 1 counts as 1
        public int TablesInModel = 1;                                    // D_Table_1…n in the shop on show (GameFlow)

        /// <summary>What was bought today, for the settlement page: (what, price in 1/100 文).</summary>
        public readonly List<(string what, int price)> BoughtToday = new();

        /// <summary>放置区: finished dishes waiting to be carried out (null = empty tray).</summary>
        public readonly (Recipe dish, Quality q)?[] Trays = new (Recipe, Quality)?[TrayCount];

        // what the last settlement brought, for the settlement page
        public int XpBefore;
        public List<Recipe> NewlyOpened = new();
        public StageInfo StageBefore;

        public static long NowMs => (long)(Time.timeAsDouble * 1000.0);
        public StageInfo Stage => Data.StageFor(Xp);

        public GameSession()
        {
            Data = GameData.Parse(Resources.Load<TextAsset>("GameData").text);
            Service = new Service(Data, new System.Random());
            Premises = new Premises(Data);
            Cash = Data.StartCash;
            for (int i = 0; i < CookRules.StoveBlocks; i++) Stoves.Add(new Stove(StoveTier.Basic, unlocked: false));
            OpenStoves();
        }

        /// <summary>The stove's blocks open by 声望: one at 一级①, one more with each upgrade, all four from 二级 on.</summary>
        public void OpenStoves()
        {
            int open = CookRules.StovesOpen(Data.Stages.IndexOf(Stage));
            for (int i = 0; i < Stoves.Count; i++) Stoves[i].Unlocked = i < open;
        }

        public IEnumerable<Recipe> OpenRecipes() =>
            Data.Recipes.Where(r => r.ShopLevel == 1 && r.IsOpen(Xp, Flags));

        /// <summary>The tables guests may sit at today, 0-based (the shop's D_Table_&lt;t+1&gt;): bought, open, and in the shop on show.</summary>
        public List<int> SeatTables() =>
            Premises.OpenTables(Day.Day).Where(n => n <= TablesInModel).Select(n => n - 1).ToList();

        public void OpenShop()
        {
            long now = NowMs;
            Day.Open(now);
            Service.StartDay(now, Stage, SeatTables(), OpenRecipes(), Reputation);
        }

        /// <summary>The next morning: an upgrade at the last settlement opens its stove block now.</summary>
        public void NextDay()
        {
            Day.NextDay();
            OpenStoves();
            BoughtToday.Clear();
        }

        // ------------------------------------------------------------------ 添置桌椅

        /// <summary>The next table or the 二楼, and whether the stage allows it yet (null: nothing left, or the 二楼 opens tomorrow).</summary>
        public Offer NextOffer => Premises.Next(Stage, Day.Day);

        /// <summary>Something can be bought this very moment: the stage allows it, the money is there, it isn't 打烊结算.</summary>
        public bool CanBuyNow => NextOffer is { Allowed: true } o && Cash >= o.Price && Day.Phase != DayPhase.Settlement;

        /// <summary>
        /// Buys the next table or the 二楼 with 雅间一. A table stands at once and, while the shop is open, takes the next
        /// guests; the 二楼 is built now and opens tomorrow. False, and nothing changes, if it isn't the next thing for sale,
        /// the stage doesn't allow it yet, the money isn't there, or the day is being settled.
        /// </summary>
        public bool Buy(Offer o)
        {
            var next = NextOffer;
            if (o == null || next == null || next.Kind != o.Kind || next.Table != o.Table || !next.Allowed ||
                Cash < next.Price || Day.Phase == DayPhase.Settlement) return false;
            Cash -= next.Price;
            Premises.Buy(next, Day.Day);
            BoughtToday.Add((OfferName(next), next.Price));
            if (Day.Phase == DayPhase.Service && next.Kind == OfferKind.Table && next.Table <= TablesInModel)
                Service.OpenTable(next.Table - 1);
            return true;
        }

        /// <summary>What an offer is called on the page and in the settlement: 第 2 张桌, 扩建二楼与雅间, 雅间二.</summary>
        public string OfferName(Offer o) =>
            o.Kind == OfferKind.Expansion ? "扩建二楼与雅间" :
            Premises.Place(o.Table) == "雅间二" ? "雅间二" : $"第 {o.Table} 张桌";

        /// <summary>Per frame while open: guests arrive, wait, eat and pay; the day ends by itself once
        /// the door has shut and the last table has paid.</summary>
        public void Tick()
        {
            if (Day.Phase != DayPhase.Service) return;
            long now = NowMs;
            Day.Tick(now);
            Service.Tick(now, Day.DoorOpen(now));
            if (!Day.DoorOpen(now) && Service.AllDone) CloseShop();
        }

        /// <summary>提前打烊 is fine once nobody is seated or waiting at the door.</summary>
        public bool CanCloseEarly => Day.Phase == DayPhase.Service && Service.AllDone;

        public void CloseShop()
        {
            long now = NowMs;
            Day.Close(now);
            StageBefore = Stage;
            XpBefore = Xp;
            var before = OpenRecipes().ToList();
            Xp += Service.Xp;
            Cash += Service.Revenue;
            NewlyOpened = OpenRecipes().Where(r => !before.Contains(r)).ToList();
            Reputation = 0.6 + 0.4 * Service.GoodRate;                    // 口碑系数 for tomorrow
        }

        public bool AnyStoveCooking()
        {
            long now = NowMs;
            return Stoves.Any(s => s.State(now) is StoveState.Cooking or StoveState.Burning);
        }

        public bool AnyTrayWaiting => Trays.Any(t => t != null && t.Value.q != Quality.Burnt && PendingCount(t.Value.dish) > 0);

        public int PendingCount(Recipe r) => Service.Pending().Count(x => x.plate.Dish.Id == r.Id);

        public int FreeTray() => System.Array.FindIndex(Trays, t => t == null);

        /// <summary>出锅 but not yet 装盘: the finished dish in each stove's wok (null = none), and when it came out.
        /// The stove is free again, but nothing new goes into its wok until this is plated.</summary>
        public readonly (Recipe dish, Quality q, long atMs)?[] InWok = new (Recipe, Quality, long)?[CookRules.StoveBlocks];

        /// <summary>自动装盘 (the player's switch): a finished dish goes onto a free tray by itself, AutoPlateMs after 出锅.</summary>
        public bool AutoPlate;
        public const int AutoPlateMs = 1200;

        /// <summary>装盘 happened: (stove, tray), for the cooking screen to fly the dish across.</summary>
        public event System.Action<int, int> Plated;

        public bool AnyWokDone => InWok.Any(w => w != null);

        /// <summary>出锅 by hand: judge and count; the finished dish stays in the wok until 装盘 (Plate).</summary>
        public (Recipe dish, Quality q, string achievement, bool autoUnlocked) TakeOut(Stove s)
        {
            var dish = s.Dish;
            var q = s.TakeOut(NowMs, byHand: true);
            string ach = null;
            if (q == Quality.Underdone && Achievements.Add("有点生")) ach = "有点生";
            if (q == Quality.Burnt && Achievements.Add("糊啦！")) ach = "糊啦！";
            bool auto = Book.RecordHandCooked(dish, q);
            if (Day.Phase == DayPhase.Service) Day.RecordServed(q);
            InWok[Stoves.IndexOf(s)] = (dish, q, NowMs);
            return (dish, q, ach, auto);
        }

        /// <summary>装盘: the finished dish in stove i's wok onto a free tray. False when there is nothing to plate or
        /// no tray is free.</summary>
        public bool Plate(int i)
        {
            if (InWok[i] == null) return false;
            int tray = FreeTray();
            if (tray < 0) return false;
            var (dish, q, _) = InWok[i].Value;
            Trays[tray] = (dish, q);
            InWok[i] = null;
            Plated?.Invoke(i, tray);
            return true;
        }

        /// <summary>Per frame: with 自动装盘 on, every finished dish is plated a moment after 出锅 (once a tray is free).</summary>
        public void TickKitchen()
        {
            if (!AutoPlate) return;
            long now = NowMs;
            for (int i = 0; i < InWok.Length; i++)
                if (InWok[i] is { } w && now - w.atMs >= AutoPlateMs) Plate(i);
        }

        /// <summary>
        /// Tap a tray: carry the dish to the oldest table waiting for it. 糊菜 is thrown away. A dish
        /// nobody has ordered stays on the tray unless `discard` (a second tap) says to throw it out.
        /// Returns what happened, for the toast; `kept` is true when the dish is still on the tray.
        /// </summary>
        public (string msg, bool kept) ServeTray(int i, bool discard)
        {
            if (Trays[i] == null) return (null, false);
            var (dish, q) = Trays[i].Value;
            var target = Service.Pending().FirstOrDefault(x => x.plate.Dish.Id == dish.Id);
            if (q != Quality.Burnt && target.plate == null && !discard)
                return ($"还没有客人点{dish.Name}，先放着（再点一次倒掉）", true);
            Trays[i] = null;
            if (q == Quality.Burnt || target.plate == null)
            {
                Service.Deliver(dish, Quality.Burnt, NowMs);   // counts as wasted
                return (q == Quality.Burnt ? $"{dish.Name}糊了，倒掉重做" : $"{dish.Name}倒掉了", false);
            }
            Service.Deliver(dish, q, NowMs);
            return ($"{dish.Name}端给 {target.party.Table + 1} 号桌", false);
        }
    }
}
