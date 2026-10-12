using System.Collections.Generic;
using System.Linq;
using BianHe.Core;
using UnityEngine;

namespace BianHe
{
    /// <summary>
    /// Everything that outlives a screen: design data, stoves (they keep cooking while the player is
    /// back in the hall), the 放置区 trays, the guests of the day, money, experience, 自动做菜
    /// counters, the tables bought, the storeroom and the morning's market, the business day and
    /// first-time achievements.
    /// </summary>
    public class GameSession
    {
        public const int TrayCount = 3;

        public readonly GameData Data;
        public readonly CookBook Book = new() { Counting = false };   // 初始·1桌 is 第一关: nothing counts yet
        public readonly BusinessDay Day = new();
        public readonly Service Service;
        public readonly Premises Premises;                               // the tables bought and the 二楼
        public readonly Pantry Pantry;                                   // the storeroom: 采购、验货、库存
        public readonly MarketDay Market = new();                        // who came down at the market this morning
        public readonly System.Random Rng = new();                       // the market's and the storeroom's chances

        /// <summary>
        /// 自动验货: deliveries are inspected for the chef, missing a twentieth of the bad portions (found at 出锅). The
        /// design gives it to a 3 级 小二 and has the player inspect by hand before that; the game has no 小二 yet and no
        /// art for bad goods, so for now it is on from the start (the user asked for it, 2026-10-12).
        /// </summary>
        public bool AutoInspect = true;
        public readonly List<Stove> Stoves = new();                      // the stove's four blocks, open by 声望 (OpenStoves)
        public readonly HashSet<string> Achievements = new();
        public readonly HashSet<string> Flags = new();
        public int Xp;
        public int Cash;                                                 // 1/100 文
        public double Reputation = 1.0;                                  // 口碑系数; day 1 counts as 1
        public int TablesInModel = 1;                                    // D_Table_1…n in the shop on show (GameFlow)

        /// <summary>What was bought today, for the settlement page: (what, price in 1/100 文).</summary>
        public readonly List<(string what, int price)> BoughtToday = new();

        /// <summary>放置区: finished dishes waiting to be carried out (null = empty tray), and whether each was made of 优质.</summary>
        public readonly (Recipe dish, Quality q, bool premium)?[] Trays = new (Recipe, Quality, bool)?[TrayCount];

        /// <summary>The storeroom's day, for the settlement page: portions bought and what they cost, bad ones thrown out at
        /// inspection, portions used in dishes, dishes lost at 出锅 to a bad portion inspection missed, and what spoiled
        /// overnight (at the closing).</summary>
        public class FoodDay
        {
            public int Bought, Spent, Thrown, Used, LostAtWok, AutoCooked;
            public Dictionary<string, int> Spoiled = new();
        }

        public FoodDay Food = new();

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
            Pantry = new Pantry(Data);
            Service.CanOffer = CanOffer;
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
            Market.NextDay();
            Food = new FoodDay();
            Book.Counting = Day.Day >= 2;   // 自动做菜 counts from 第二关, the second day's first table on
        }

        // ------------------------------------------------------------------ 采购、验货与库存

        /// <summary>What the market sells at this point (by experience), vendor by vendor: the market's own goods (the
        /// 时空门's modern food and the wine merchant come later).</summary>
        public List<IGrouping<string, Ingredient>> MarketGoods() =>
            Data.Ingredients.Values.Where(i => i.Source == "market" && i.Condition == null && Xp >= i.MinXp)
                .GroupBy(i => i.Vendor).ToList();

        /// <summary>The open dishes that use an ingredient.</summary>
        public IEnumerable<Recipe> DishesUsing(string id) =>
            OpenRecipes().Where(r => r.Ingredients.ContainsKey(id) || r.Seasonings.ContainsKey(id));

        /// <summary>Main ingredients an order adds to the storeroom (what the stage's cap counts).</summary>
        public int MainPortions(IEnumerable<OrderLine> order) => order.Where(l => Data.Ingredients[l.Id].IsMain).Sum(l => l.Qty);

        /// <summary>
        /// Buys a market order and takes delivery, inspected at once (自动验货 lets a twentieth of the bad portions through,
        /// to be found at 出锅). Null, and nothing bought, if it costs more than there is or would put the storeroom over
        /// the stage's cap on main ingredients.
        /// </summary>
        public List<Arrival> BuyFood(List<OrderLine> order)
        {
            int cost = Pantry.Total(order, Market.Discount);
            if (cost <= 0 || cost > Cash || Pantry.MainCount + MainPortions(order) > Stage.InventoryCap) return null;
            Cash -= cost;
            var got = Pantry.Receive(order, Market.Discount, AutoInspect ? Data.Procurement.AutoInspectionMiss : 0, Rng);
            Food.Bought += got.Sum(a => a.Bought);
            Food.Spent += cost;
            Food.Thrown += got.Sum(a => a.Found);
            return got;
        }

        /// <summary>Asks a vendor to come down (once a day each): true if he does.</summary>
        public bool Bargain(string vendor, int option) => Market.Bargain(vendor, option, Data.Procurement, Rng);

        /// <summary>
        /// Starts a dish on stove k, its ingredients taken off the shelf at once: not if the stove can't take it, or if
        /// anything is short (shortOf says what). The dish counts as 优质 if all its main ingredients were; a bad portion
        /// inspection missed, if one is among them, is found when it comes out.
        /// </summary>
        public Stove.StartResult StartDish(int k, Recipe dish, out List<string> shortOf)
        {
            var s = Stoves[k];
            shortOf = Pantry.Short(dish).ToList();
            if (!s.Unlocked) return Stove.StartResult.Locked;
            if (s.Dish != null) return Stove.StartResult.Busy;
            if (!CookRules.CanCook(s.Tier, dish.Difficulty)) return Stove.StartResult.TierTooLow;
            if (shortOf.Count > 0) return Stove.StartResult.Short;
            var taken = Pantry.Take(dish, Rng);
            s.Start(dish, NowMs);
            s.Premium = taken.Premium;
            s.Spoiled = taken.Bad;
            Food.Used += dish.Ingredients.Values.Sum();
            return Stove.StartResult.Ok;
        }

        /// <summary>The guests only order what the storeroom can still make: this dish after the ones listed (the party's
        /// orders so far) and after every order already waiting for the kitchen.</summary>
        bool CanOffer(Recipe r, IReadOnlyList<Recipe> before) => Pantry.Has(r, OrdersAhead().Concat(before));

        /// <summary>The dishes ordered and not started: every plate still to come at a table or at the door, less, dish by
        /// dish, those already cooking, out in a wok or on a tray (their ingredients are off the shelf already).</summary>
        IEnumerable<Recipe> OrdersAhead()
        {
            var inHand = new Dictionary<string, int>();
            void Count(Recipe r) => inHand[r.Id] = (inHand.TryGetValue(r.Id, out var n) ? n : 0) + 1;
            foreach (var s in Stoves) if (s.Dish != null) Count(s.Dish);
            foreach (var w in InWok) if (w != null && w.Value.q != Quality.Burnt) Count(w.Value.dish);
            foreach (var t in Trays) if (t != null && t.Value.q != Quality.Burnt) Count(t.Value.dish);
            foreach (var p in Service.Parties.Where(p => p.State is PartyState.AtDoor or PartyState.Waiting))
                foreach (var pl in p.Plates.Where(x => !x.Served))
                {
                    if (inHand.TryGetValue(pl.Dish.Id, out var n) && n > 0) inHand[pl.Dish.Id] = n - 1;
                    else yield return pl.Dish;
                }
        }

        /// <summary>For the screenshot and video runs: enough of everything the open dishes need, none of it bad.</summary>
        public void StockForDemo() => Pantry.Fill(OpenRecipes(), 30);

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
            Food.Spoiled = Pantry.Overnight(Rng);                          // 过夜: what is left spoils at its rate
        }

        /// <summary>A wok of the player's is on the fire (自动做菜's look after themselves).</summary>
        public bool AnyStoveCooking()
        {
            long now = NowMs;
            return Stoves.Where((s, i) => !AutoStove[i]).Any(s => s.State(now) is StoveState.Cooking or StoveState.Burning);
        }

        public bool AnyTrayWaiting => Trays.Any(t => t != null && t.Value.q != Quality.Burnt && PendingCount(t.Value.dish) > 0);

        public int PendingCount(Recipe r) => Service.Pending().Count(x => x.plate.Dish.Id == r.Id);

        public int FreeTray() => System.Array.FindIndex(Trays, t => t == null);

        /// <summary>出锅 but not yet 装盘: the finished dish in each stove's wok (null = none), when it came out, and whether
        /// it was made of 优质. The stove is free again, but nothing new goes into its wok until this is plated.</summary>
        public readonly (Recipe dish, Quality q, long atMs, bool premium)?[] InWok = new (Recipe, Quality, long, bool)?[CookRules.StoveBlocks];

        /// <summary>自动装盘 (the player's switch): a finished dish goes onto a free tray by itself, AutoPlateMs after 出锅.</summary>
        public bool AutoPlate;
        public const int AutoPlateMs = 1200;

        /// <summary>装盘 happened: (stove, tray), for the cooking screen to fly the dish across.</summary>
        public event System.Action<int, int> Plated;

        public bool AnyWokDone => InWok.Where((w, i) => !AutoStove[i]).Any(w => w != null);

        /// <summary>出锅 by hand: judge and count; the finished dish stays in the wok until 装盘 (Plate). A bad portion that
        /// got past inspection is found now: the dish is lost (spoiled), nothing stays in the wok and nothing counts.</summary>
        public (Recipe dish, Quality q, string achievement, bool autoUnlocked, bool spoiled) TakeOut(Stove s)
        {
            var dish = s.Dish;
            bool premium = s.Premium, spoiled = s.Spoiled;
            var q = s.TakeOut(NowMs, byHand: true);
            if (spoiled)
            {
                Food.LostAtWok++;
                Service.Deliver(dish, Quality.Burnt, NowMs);   // counts as wasted
                return (dish, q, null, false, true);
            }
            string ach = null;
            if (q == Quality.Underdone && Achievements.Add("有点生")) ach = "有点生";
            if (q == Quality.Burnt && Achievements.Add("糊啦！")) ach = "糊啦！";
            bool auto = Book.RecordHandCooked(dish, q);
            if (Day.Phase == DayPhase.Service) Day.RecordServed(q);
            InWok[Stoves.IndexOf(s)] = (dish, q, NowMs, premium);
            return (dish, q, ach, auto, false);
        }

        /// <summary>装盘: the finished dish in stove i's wok onto a free tray. False when there is nothing to plate or
        /// no tray is free.</summary>
        public bool Plate(int i)
        {
            if (InWok[i] == null) return false;
            int tray = FreeTray();
            if (tray < 0) return false;
            var (dish, q, _, premium) = InWok[i].Value;
            Trays[tray] = (dish, q, premium);
            InWok[i] = null;
            Plated?.Invoke(i, tray);
            return true;
        }

        /// <summary>The stoves 自动做菜 is using: the dish on it cooks by itself, comes out at its time and goes onto a tray.</summary>
        public readonly bool[] AutoStove = new bool[CookRules.StoveBlocks];

        /// <summary>The stoves the player is putting a dish together in (the cooking screen says so): auto-cook leaves them.</summary>
        public readonly bool[] Preparing = new bool[CookRules.StoveBlocks];

        /// <summary>
        /// Per frame. 自动做菜 (《玩法与数值》02): once a dish has been cooked well by hand often enough, its orders go onto
        /// free stoves by themselves (open ones good enough for it, not one the player is filling), at most two at a time,
        /// while the storeroom has what it takes; each comes out at its ready time as auto-cook makes it and goes onto a
        /// free tray as soon as there is one (a bad portion that got past inspection is found then, and the dish is lost).
        /// With 自动装盘 on, the player's own dishes are plated a moment after 出锅 too.
        /// </summary>
        public void TickKitchen()
        {
            long now = NowMs;
            for (int i = 0; i < Stoves.Count; i++)
            {
                var s = Stoves[i];
                if (!AutoStove[i]) continue;
                if (s.Dish != null && now >= s.ReadyMs)
                {
                    var dish = s.Dish;
                    bool premium = s.Premium, spoiled = s.Spoiled;
                    var q = s.AutoTakeOut();
                    if (spoiled)
                    {
                        Food.LostAtWok++;
                        Service.Deliver(dish, Quality.Burnt, now);   // counts as wasted
                        AutoStove[i] = false;
                        continue;
                    }
                    if (Day.Phase == DayPhase.Service) Day.RecordServed(q);
                    Food.AutoCooked++;
                    InWok[i] = (dish, q, now, premium);
                }
                if (s.Dish == null && InWok[i] != null && Plate(i)) AutoStove[i] = false;
                else if (s.Dish == null && InWok[i] == null) AutoStove[i] = false;
            }
            if (Day.Phase == DayPhase.Service)
            {
                int busy = AutoStove.Count(a => a);
                while (busy < CookRules.MaxAutoStoves)
                {
                    var dish = OrdersAhead().FirstOrDefault(r => Book.IsAuto(r) && Pantry.Has(r));
                    if (dish == null) break;
                    int k = Enumerable.Range(0, Stoves.Count).Where(j => !AutoStove[j] && !Preparing[j] && InWok[j] == null &&
                        Stoves[j].State(now) == StoveState.Idle && CookRules.CanCook(Stoves[j].Tier, dish.Difficulty)).DefaultIfEmpty(-1).First();
                    if (k < 0 || StartDish(k, dish, out _) != Stove.StartResult.Ok) break;
                    AutoStove[k] = true;
                    busy++;
                }
            }
            if (!AutoPlate) return;
            for (int i = 0; i < InWok.Length; i++)
                if (!AutoStove[i] && InWok[i] is { } w && now - w.atMs >= AutoPlateMs) Plate(i);
        }

        /// <summary>
        /// Tap a tray: carry the dish to the oldest table waiting for it. 糊菜 is thrown away. A dish
        /// nobody has ordered stays on the tray unless `discard` (a second tap) says to throw it out.
        /// Returns what happened, for the toast; `kept` is true when the dish is still on the tray.
        /// </summary>
        public (string msg, bool kept) ServeTray(int i, bool discard)
        {
            if (Trays[i] == null) return (null, false);
            var (dish, q, premium) = Trays[i].Value;
            var target = Service.Pending().FirstOrDefault(x => x.plate.Dish.Id == dish.Id);
            if (q != Quality.Burnt && target.plate == null && !discard)
                return ($"还没有客人点{dish.Name}，先放着（再点一次倒掉）", true);
            Trays[i] = null;
            if (q == Quality.Burnt || target.plate == null)
            {
                Service.Deliver(dish, Quality.Burnt, NowMs);   // counts as wasted
                return (q == Quality.Burnt ? $"{dish.Name}糊了，倒掉重做" : $"{dish.Name}倒掉了", false);
            }
            Service.Deliver(dish, q, NowMs, premium);
            return ($"{dish.Name}端给 {target.party.Table + 1} 号桌", false);
        }
    }
}
