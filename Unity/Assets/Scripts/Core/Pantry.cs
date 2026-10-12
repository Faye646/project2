using System;
using System.Collections.Generic;
using System.Linq;

namespace BianHe.Core
{
    public enum Grade { Normal, Premium }

    /// <summary>A batch on the shelf: portions of one ingredient at one grade, what each cost, and how many of them are bad
    /// ones inspection let through (they are found when the dish comes out of the wok).</summary>
    public class Lot
    {
        public string Id;
        public Grade Grade;
        public int Count, HiddenBad, UnitCost;
    }

    /// <summary>One line of a market order.</summary>
    public class OrderLine
    {
        public string Id;
        public Grade Grade;
        public int Qty;
    }

    /// <summary>How one line of an order came in: bought, bad among them, found (and thrown out) by inspection, and what each
    /// cost; the rest went on the shelf.</summary>
    public class Arrival
    {
        public string Id;
        public Grade Grade;
        public int Bought, Bad, Found, UnitPrice;
        public int Kept => Bought - Found;
    }

    /// <summary>What a dish took off the shelf: what it cost, whether all its main ingredients were 优质, and whether a bad
    /// portion inspection missed was among them (then the dish is lost when it comes out).</summary>
    public class Taken
    {
        public bool Premium, Bad;
        public int Cost;
    }

    /// <summary>
    /// The market this morning (《玩法与数值》06 采购): each vendor can be asked once a day to come down; if he does, all he
    /// sells today is that much cheaper; if not, he keeps to his price for the day.
    /// </summary>
    public class MarketDay
    {
        readonly Dictionary<string, double> discount = new();
        readonly HashSet<string> asked = new();

        public double Discount(string vendor) => vendor != null && discount.TryGetValue(vendor, out var d) ? d : 0;
        public bool Asked(string vendor) => asked.Contains(vendor);

        /// <summary>Asks a vendor with one of the lines (ProcurementRules.Bargains): true if he comes down.</summary>
        public bool Bargain(string vendor, int option, ProcurementRules rules, Random rng)
        {
            if (asked.Contains(vendor) || option < 0 || option >= rules.Bargains.Count) return false;
            asked.Add(vendor);
            var (_, cut, odds) = rules.Bargains[option];
            if (rng.NextDouble() >= odds) return false;
            discount[vendor] = cut;
            return true;
        }

        public void NextDay()
        {
            discount.Clear();
            asked.Clear();
        }
    }

    /// <summary>
    /// The storeroom (库存, 《玩法与数值》06), by batch: market prices (普通 or 优质; a heap of one main ingredient cheaper; the
    /// vendor's bargain; never under seven tenths of the list price), delivery with inspection (the bad portions found
    /// are thrown out, the ones missed go on the shelf to be found at 出锅), taking a dish's worth at once (all or nothing),
    /// and the night (what is left spoils at its rate). The stage's cap on main ingredients is the caller's to check.
    /// Pure logic: chance comes from the given Random.
    /// </summary>
    public class Pantry
    {
        readonly GameData data;
        public readonly List<Lot> Lots = new();

        public Pantry(GameData data) => this.data = data;

        ProcurementRules Rules => data.Procurement;
        Ingredient Ing(string id) => data.Ingredients[id];

        public int Count(string id) => Lots.Where(l => l.Id == id).Sum(l => l.Count);
        public int Count(string id, Grade g) => Lots.Where(l => l.Id == id && l.Grade == g).Sum(l => l.Count);

        /// <summary>Portions of main ingredients on the shelf: what the stage's cap counts.</summary>
        public int MainCount => Lots.Where(l => Ing(l.Id).IsMain).Sum(l => l.Count);

        // ------------------------------------------------------------------ 采购

        /// <summary>
        /// What one portion costs in an order of qty with the vendor's bargain (0: none): 普通 is the list price, less the
        /// heap discount for a market main ingredient, less the bargain; 优质 is its own price less the bargain; never under
        /// 0.7 of the list price; rounded up to the accounting unit (1/100 文).
        /// </summary>
        public int UnitPrice(Ingredient i, Grade g, int qty, double bargain)
        {
            int list = g == Grade.Premium && i.HasPremium ? i.PremiumCost : i.UnitCost;
            double k = 1.0 - bargain;
            if (g == Grade.Normal && Heaps(i)) k *= BulkFactor(qty);
            return (int)Math.Ceiling(list * Math.Max(Rules.Floor, k) - 1e-9);
        }

        /// <summary>The heap discount is for the market's main ingredients (not seasonings, wine or modern food).</summary>
        static bool Heaps(Ingredient i) => i.IsMain && i.Source == "market";

        double BulkFactor(int qty)
        {
            double k = 1.0;
            foreach (var kv in Rules.Bulk)
                if (qty >= kv.Key) k = kv.Value;
            return k;
        }

        /// <summary>How often a portion comes bad: the grade's rate, five points more at the bottom of a heap of ten or more
        /// (for what comes bad at all).</summary>
        public double BadRate(Ingredient i, Grade g, int qty)
        {
            double r = g == Grade.Premium && i.HasPremium ? i.BadRatePremium : i.BadRate;
            if (g == Grade.Normal && r > 0 && Heaps(i) && qty >= Rules.BulkBadThreshold) r += Rules.BulkBadAdd;
            return r;
        }

        /// <summary>What an order costs in all.</summary>
        public int Total(IEnumerable<OrderLine> order, Func<string, double> bargainOf) =>
            order.Where(l => l.Qty > 0).Sum(l => UnitPrice(Ing(l.Id), l.Grade, l.Qty, bargainOf(Ing(l.Id).Vendor)) * l.Qty);

        /// <summary>
        /// Takes delivery of an order and inspects it: each portion comes bad at its rate, and each bad one is found and
        /// thrown out unless inspection misses it (missRate: 自动验货 0.05). What is kept goes on the shelf, the bad ones
        /// missed among it.
        /// </summary>
        public List<Arrival> Receive(IEnumerable<OrderLine> order, Func<string, double> bargainOf, double missRate, Random rng)
        {
            var got = new List<Arrival>();
            foreach (var line in order.Where(l => l.Qty > 0))
            {
                var i = Ing(line.Id);
                var a = new Arrival { Id = line.Id, Grade = line.Grade, Bought = line.Qty, UnitPrice = UnitPrice(i, line.Grade, line.Qty, bargainOf(i.Vendor)) };
                double rate = BadRate(i, line.Grade, line.Qty);
                for (int k = 0; k < line.Qty; k++)
                    if (rng.NextDouble() < rate)
                    {
                        a.Bad++;
                        if (rng.NextDouble() >= missRate) a.Found++;
                    }
                if (a.Kept > 0)
                    Lots.Add(new Lot { Id = a.Id, Grade = a.Grade, Count = a.Kept, HiddenBad = a.Bad - a.Found, UnitCost = a.UnitPrice });
                got.Add(a);
            }
            return got;
        }

        // ------------------------------------------------------------------ 做菜

        static IEnumerable<KeyValuePair<string, int>> Needs(Recipe r) => r.Ingredients.Concat(r.Seasonings).Where(kv => kv.Value > 0);

        /// <summary>Is a dish's worth on the shelf, after what the dishes in `before` take first?</summary>
        public bool Has(Recipe r, IEnumerable<Recipe> before = null)
        {
            var need = new Dictionary<string, int>();
            foreach (var x in (before ?? Enumerable.Empty<Recipe>()).Append(r))
                foreach (var kv in Needs(x))
                    need[kv.Key] = (need.TryGetValue(kv.Key, out var n) ? n : 0) + kv.Value;
            return need.All(kv => Count(kv.Key) >= kv.Value);
        }

        /// <summary>How many of a dish the shelf holds.</summary>
        public int Portions(Recipe r) => Needs(r).Select(kv => Count(kv.Key) / kv.Value).DefaultIfEmpty(0).Min();

        /// <summary>What a dish lacks on the shelf, by ingredient.</summary>
        public IEnumerable<string> Short(Recipe r) => Needs(r).Where(kv => Count(kv.Key) < kv.Value).Select(kv => kv.Key);

        /// <summary>
        /// Takes a dish's worth off the shelf at once, or nothing (null) if anything is short. Its main ingredients come
        /// 优质 if every one of them has enough 优质 on the shelf (the dish then counts as 优质), else 普通 first; within a
        /// grade the oldest batch first. A portion is one of the bad ones inspection missed with the odds of its batch.
        /// </summary>
        public Taken Take(Recipe r, Random rng)
        {
            if (!Has(r)) return null;
            var mains = r.Ingredients.Where(kv => kv.Value > 0).ToList();
            bool premium = mains.Count > 0 && mains.All(kv => Count(kv.Key, Grade.Premium) >= kv.Value);
            var taken = new Taken { Premium = premium };
            foreach (var kv in Needs(r).ToList())
                for (int n = 0; n < kv.Value; n++)
                {
                    var first = premium && r.Ingredients.ContainsKey(kv.Key) ? Grade.Premium : Grade.Normal;
                    var lot = Lots.FirstOrDefault(l => l.Id == kv.Key && l.Grade == first && l.Count > 0)
                              ?? Lots.First(l => l.Id == kv.Key && l.Count > 0);
                    if (lot.HiddenBad > 0 && rng.NextDouble() < lot.HiddenBad / (double)lot.Count)
                    {
                        lot.HiddenBad--;
                        taken.Bad = true;
                    }
                    lot.Count--;
                    taken.Cost += lot.UnitCost;
                }
            Lots.RemoveAll(l => l.Count <= 0);
            return taken;
        }

        // ------------------------------------------------------------------ 打烊

        /// <summary>过夜: each portion left spoils at its ingredient's overnight rate and is taken off (no need to inspect it
        /// again); returns how many of each.</summary>
        public Dictionary<string, int> Overnight(Random rng)
        {
            var spoiled = new Dictionary<string, int>();
            foreach (var lot in Lots)
            {
                double rate = Ing(lot.Id).OvernightBad;
                if (rate <= 0) continue;
                int gone = 0, badGone = 0;
                for (int k = 0; k < lot.Count; k++)
                {
                    if (rng.NextDouble() >= rate) continue;
                    // a spoiled portion is as likely one of the hidden bad ones as any other
                    if (lot.HiddenBad - badGone > 0 && rng.NextDouble() < (lot.HiddenBad - badGone) / (double)(lot.Count - gone)) badGone++;
                    gone++;
                }
                if (gone == 0) continue;
                lot.HiddenBad -= badGone;
                lot.Count -= gone;
                spoiled[lot.Id] = (spoiled.TryGetValue(lot.Id, out var n) ? n : 0) + gone;
            }
            Lots.RemoveAll(l => l.Count <= 0);
            return spoiled;
        }

        /// <summary>For the screenshot runs: at least this many of everything these dishes need, none of it bad.</summary>
        public void Fill(IEnumerable<Recipe> dishes, int portions)
        {
            foreach (var id in dishes.SelectMany(Needs).Select(kv => kv.Key).Distinct().ToList())
                if (Count(id) < portions)
                    Lots.Add(new Lot { Id = id, Grade = Grade.Normal, Count = portions - Count(id), UnitCost = Ing(id).UnitCost });
        }
    }
}
