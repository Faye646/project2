using System;
using System.Collections.Generic;
using System.Linq;

namespace BianHe.Core
{
    public enum Review { Good, Normal, Bad }

    public enum PartyState { AtDoor, Waiting, Dining, Paid, LeftAtDoor, LeftAngry }

    /// <summary>One portion a guest ordered; filled when a dish comes out of the kitchen.</summary>
    public class Plate
    {
        public Recipe Dish;
        public bool Served;
        public Quality Quality;
    }

    public class Guest
    {
        public string Type;
        public readonly List<Plate> Plates = new();
        public Review? Review;
    }

    /// <summary>A group of guests (一桌客人) from the door to the bill.</summary>
    public class Party
    {
        public int Id;
        public string Type;
        public readonly List<Guest> Guests = new();
        public PartyState State;
        public int Table = -1;
        public long ArrivedMs, OrderedMs, PatienceMs, DiningEndsMs;
        public bool Late;          // 催单: patience ran out before everything was served
        public int Bill, Xp;

        public IEnumerable<Plate> Plates => Guests.SelectMany(g => g.Plates);
        public int HardestDifficulty => Plates.Max(p => p.Dish.Difficulty);
        public bool AllServed => Plates.All(p => p.Served);
        public long WaitedMs(long now) => now - OrderedMs;
        public long LeaveAtMs => OrderedMs + PatienceMs + ServiceRules.LeaveAfterLateMs;
    }

    /// <summary>
    /// Numbers from 《玩法与数值》03 and rules.service in the design data: patience, dining time,
    /// review odds and modifiers, experience per guest.
    /// </summary>
    public static class ServiceRules
    {
        public const long DoorWaitMs = 10_000;
        public const long LeaveAfterLateMs = 15_000;

        /// <summary>耐心 = 基础 (by the hardest dish: 25/35/45 s) + 5 s per extra guest.</summary>
        public static long PatienceMs(int hardestDifficulty, int guests) =>
            (hardestDifficulty switch { 1 => 25_000, 2 => 35_000, _ => 45_000 }) + 5_000L * Math.Max(0, guests - 1);

        /// <summary>用餐时长 by the hardest dish: 30/40/50 s.</summary>
        public static long DiningMs(int hardestDifficulty) => hardestDifficulty switch { 1 => 30_000, 2 => 40_000, _ => 50_000 };

        public static (double good, double normal, double bad) BaseOdds(Quality q) => q switch
        {
            Quality.Immortal => (1.0, 0.0, 0.0),
            Quality.Perfect => (0.70, 0.25, 0.05),
            Quality.Good => (0.60, 0.35, 0.05),
            Quality.Underdone => (0.20, 0.40, 0.40),
            _ => (0.0, 0.20, 0.80),
        };

        /// <summary>
        /// Applies percentage-point modifiers to 好评: a bonus is taken from 一般 first, then 差评; a
        /// penalty moves to 一般. Every column stays within 0–1.
        /// </summary>
        public static (double good, double normal, double bad) Modify((double good, double normal, double bad) o, double goodPp)
        {
            double d = goodPp / 100.0;
            if (d >= 0)
            {
                d = Math.Min(d, o.normal + o.bad);
                double fromNormal = Math.Min(d, o.normal);
                return (o.good + d, o.normal - fromNormal, o.bad - (d - fromNormal));
            }
            double take = Math.Min(-d, o.good);
            return (o.good - take, o.normal + take, o.bad);
        }

        public static Review Draw((double good, double normal, double bad) o, double roll) =>
            roll < o.good ? Review.Good : roll < o.good + o.normal ? Review.Normal : Review.Bad;

        /// <summary>降一档: 好评→一般, 一般→差评, 差评 stays.</summary>
        public static Review ShiftDown(Review r) => r == Review.Good ? Review.Normal : Review.Bad;

        public static int Xp(Review r) => r switch { Review.Good => 6, Review.Normal => 4, _ => 2 };

        public static string Name(Review r) => r switch { Review.Good => "好评", Review.Normal => "一般", _ => "差评" };

        /// <summary>口味合心意: the dish hits a preference (temperature counts) and no avoided tag.</summary>
        public static bool TasteMatch(Recipe r, CustomerProfile p) =>
            (p.Prefer.Contains(r.Temperature) || r.TasteTags.Any(p.Prefer.Contains)) && !r.TasteTags.Any(p.Avoid.Contains);
    }

    /// <summary>
    /// 营业中的客人: arrivals at the stage's pace, seating, ordering, patience, dining, the bill and the
    /// reviews. Pure logic; time comes in from the caller and randomness from the given Random.
    /// For now only 普通工人 come (一级①); the chef serves every dish that comes out of the stove.
    /// </summary>
    public class Service
    {
        public readonly List<Party> Parties = new();
        public readonly List<string> Log = new();
        public event Action<Party, string> Notice;

        readonly GameData data;
        readonly Random rng;
        StageInfo stage;
        int tables;
        List<Recipe> menu;
        int planned, arrived;
        long nextArrivalMs;
        double reputation;
        int nextId = 1;

        // day totals
        public int GuestsArrived => arrived;
        public int Planned => planned;
        public int Revenue, Xp, GuestsPaid, GuestsLeft, Good, Normal, Bad, Wasted;

        public Service(GameData data, Random rng)
        {
            this.data = data;
            this.rng = rng;
        }

        public void StartDay(long nowMs, StageInfo stageInfo, int tablesInShop, IEnumerable<Recipe> openMenu, double reputationFactor)
        {
            stage = stageInfo;
            tables = Math.Max(1, Math.Min(stageInfo.TableCap, tablesInShop));
            menu = openMenu.ToList();
            reputation = reputationFactor;
            planned = (int)Math.Floor(stageInfo.VisitorCap * reputationFactor);
            arrived = 0;
            Parties.Clear();
            Revenue = Xp = GuestsPaid = GuestsLeft = Good = Normal = Bad = Wasted = 0;
            nextArrivalMs = nowMs + 4_000;   // the first group shows up right after opening
        }

        public bool AllDone => Parties.All(p => p.State is PartyState.Paid or PartyState.LeftAngry or PartyState.LeftAtDoor);
        public int SeatedParties => Parties.Count(p => p.State is PartyState.Waiting or PartyState.Dining);
        public double GoodRate => Good + Normal + Bad == 0 ? 1.0 : (double)Good / (Good + Normal + Bad);

        /// <summary>Plates still to cook, oldest order first.</summary>
        public IEnumerable<(Party party, Plate plate)> Pending() =>
            Parties.Where(p => p.State == PartyState.Waiting).OrderBy(p => p.OrderedMs)
                .SelectMany(p => p.Plates.Where(pl => !pl.Served).Select(pl => (p, pl)));

        public void Tick(long now, bool doorOpen)
        {
            // arrivals
            if (doorOpen && arrived < planned && now >= nextArrivalMs)
            {
                SpawnParty(now);
                double mean = stage.ArrivalIntervalMs / Math.Max(0.6, reputation);
                nextArrivalMs = now + (long)(mean * (0.7 + 0.6 * rng.NextDouble()));
            }

            foreach (var p in Parties.ToList())
            {
                switch (p.State)
                {
                    case PartyState.AtDoor:
                        int free = FreeTable();
                        if (free >= 0) Seat(p, free, now);
                        else if (now - p.ArrivedMs > ServiceRules.DoorWaitMs)
                        {
                            p.State = PartyState.LeftAtDoor;
                            GuestsLeft += p.Guests.Count;
                            Say(p, "没有空桌，走了");
                        }
                        break;
                    case PartyState.Waiting:
                        if (!p.Late && p.WaitedMs(now) > p.PatienceMs)
                        {
                            p.Late = true;
                            Say(p, "催单了！");
                        }
                        if (now > p.LeaveAtMs)
                        {
                            p.State = PartyState.LeftAngry;
                            GuestsLeft += p.Guests.Count;
                            Wasted += p.Plates.Count(pl => pl.Served);
                            Say(p, "等不及，离店了");
                        }
                        break;
                    case PartyState.Dining:
                        if (now >= p.DiningEndsMs) Checkout(p);
                        break;
                }
            }
        }

        int FreeTable()
        {
            for (int t = 0; t < tables; t++)
                if (!Parties.Any(p => p.Table == t && p.State is PartyState.Waiting or PartyState.Dining)) return t;
            return -1;
        }

        void SpawnParty(long now)
        {
            var profile = data.Profiles["worker"];
            // 2–4 people, usually 3; never more than the day's plan allows
            int size = rng.NextDouble() switch { < 0.25 => 2, < 0.75 => 3, _ => 4 };
            size = Math.Max(1, Math.Min(size, planned - arrived));
            var party = new Party { Id = nextId++, Type = "worker", ArrivedMs = now, State = PartyState.AtDoor };
            for (int i = 0; i < size; i++) party.Guests.Add(Order(profile));
            arrived += size;
            Parties.Add(party);
            Say(party, $"{size} 位{profile.Name}进门");
        }

        /// <summary>
        /// 各点各的: each guest picks a dish within budget, favouring ones that suit their taste; if one
        /// portion is short of 90% of their appetite and money allows, they add the cheapest dish.
        /// </summary>
        Guest Order(CustomerProfile profile)
        {
            var g = new Guest { Type = profile.Id };
            int budget = profile.BudgetWen * 100;
            var affordable = menu.Where(r => r.Price <= budget).ToList();
            if (affordable.Count == 0) affordable = menu.OrderBy(r => r.Price).Take(1).ToList();
            double Weight(Recipe r) => (ServiceRules.TasteMatch(r, profile) ? 2.0 : 1.0) *
                                       (r.SuggestedGroups.Contains(profile.Id) ? 1.5 : 1.0);
            var pick = WeightedPick(affordable, Weight);
            g.Plates.Add(new Plate { Dish = pick });
            var cheapest = affordable.OrderBy(r => r.Price).First();
            if (pick.Satiety < 0.9 * profile.TargetSatiety && pick.Price + cheapest.Price <= budget)
                g.Plates.Add(new Plate { Dish = cheapest });
            return g;
        }

        Recipe WeightedPick(List<Recipe> items, Func<Recipe, double> weight)
        {
            double total = items.Sum(weight), roll = rng.NextDouble() * total;
            foreach (var r in items)
            {
                roll -= weight(r);
                if (roll <= 0) return r;
            }
            return items[^1];
        }

        void Seat(Party p, int table, long now)
        {
            p.Table = table;
            p.State = PartyState.Waiting;
            p.OrderedMs = now;   // the chef takes the order as they sit down
            p.PatienceMs = ServiceRules.PatienceMs(p.HardestDifficulty, p.Guests.Count);
            var dishes = p.Plates.GroupBy(pl => pl.Dish.Name).Select(gr => gr.Count() > 1 ? $"{gr.Key}×{gr.Count()}" : gr.Key);
            Say(p, $"{table + 1} 号桌点了 {string.Join("、", dishes)}");
        }

        /// <summary>
        /// A dish came out of the stove. It goes to the oldest waiting plate of that recipe. 糊菜 is
        /// thrown away for a remake (never served here); a dish nobody ordered is wasted.
        /// </summary>
        public bool Deliver(Recipe dish, Quality q, long now)
        {
            if (q == Quality.Burnt) { Wasted++; return false; }
            var target = Pending().FirstOrDefault(x => x.plate.Dish.Id == dish.Id);
            if (target.plate == null) { Wasted++; return false; }
            target.plate.Served = true;
            target.plate.Quality = q;
            var p = target.party;
            if (p.AllServed)
            {
                p.State = PartyState.Dining;
                p.DiningEndsMs = now + ServiceRules.DiningMs(p.HardestDifficulty);
                Say(p, $"{p.Table + 1} 号桌菜上齐了，开吃");
            }
            return true;
        }

        void Checkout(Party p)
        {
            var profile = data.Profiles[p.Type];
            foreach (var g in p.Guests)
            {
                // judged on the guest's own plate (the worst one if they ordered two)
                var plate = g.Plates.OrderBy(pl => QualityRank(pl.Quality)).First();
                double pp = g.Plates.Any(pl => ServiceRules.TasteMatch(pl.Dish, profile)) ? 15 : 0;   // 合心意 +15, once
                var r = ServiceRules.Draw(ServiceRules.Modify(ServiceRules.BaseOdds(plate.Quality), pp), rng.NextDouble());
                if (p.Late) r = ServiceRules.ShiftDown(r);
                g.Review = r;
                p.Xp += ServiceRules.Xp(r);
                if (r == Review.Good) Good++; else if (r == Review.Normal) Normal++; else Bad++;
            }
            p.Bill = p.Plates.Sum(pl => pl.Dish.Price);
            p.State = PartyState.Paid;
            Revenue += p.Bill;
            Xp += p.Xp;
            GuestsPaid += p.Guests.Count;
            int good = p.Guests.Count(g => g.Review == Review.Good);
            Say(p, $"{p.Table + 1} 号桌结账 {p.Bill / 100} 文 · 好评 {good}/{p.Guests.Count} · 经验 +{p.Xp}");
        }

        static int QualityRank(Quality q) => q switch
        {
            Quality.Burnt => 0, Quality.Underdone => 1, Quality.Good => 2, Quality.Perfect => 3, _ => 4,
        };

        void Say(Party p, string msg)
        {
            Log.Add(msg);
            Notice?.Invoke(p, msg);
        }
    }
}
