using System.Collections.Generic;
using System.Linq;
using BianHe.Core;
using UnityEngine;

namespace BianHe
{
    /// <summary>
    /// Everything that outlives a screen: design data, stoves (they keep cooking while the player is
    /// back in the hall), the 放置区 trays, the guests of the day, money, experience, 自动做菜
    /// counters, the business day and first-time achievements.
    /// </summary>
    public class GameSession
    {
        public const int TrayCount = 3;

        public readonly GameData Data;
        public readonly CookBook Book = new() { Counting = false };   // 初始·1桌 is 第一关: nothing counts yet
        public readonly BusinessDay Day = new();
        public readonly Service Service;
        public readonly List<Stove> Stoves = new();
        public readonly int[] StovePrices = { 0, 50, 80, 80 };           // 第 2 口 50；第 3、4 口各 80 文
        public readonly HashSet<string> Achievements = new();
        public readonly HashSet<string> Flags = new();
        public int Xp;
        public int Cash;                                                 // 1/100 文
        public double Reputation = 1.0;                                  // 口碑系数; day 1 counts as 1
        public int TablesInShop = 1;                                     // the shop's tables in use (GameFlow, by stage)

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
            Cash = Data.StartCash;
            for (int i = 0; i < 4; i++) Stoves.Add(new Stove(StoveTier.Basic, unlocked: i == 0));
        }

        public IEnumerable<Recipe> OpenRecipes() =>
            Data.Recipes.Where(r => r.ShopLevel == 1 && r.IsOpen(Xp, Flags));

        public void OpenShop()
        {
            long now = NowMs;
            Day.Open(now);
            Service.StartDay(now, Stage, TablesInShop, OpenRecipes(), Reputation);
        }

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
        public readonly (Recipe dish, Quality q, long atMs)?[] InWok = new (Recipe, Quality, long)?[4];

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
