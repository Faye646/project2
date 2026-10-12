using System;
using System.IO;
using System.Linq;
using BianHe.Core;
using NUnit.Framework;

namespace BianHe.Tests
{
    /// <summary>Buying, inspection, the storeroom and the night against 《玩法与数值》06 and rules.procurement.</summary>
    public class PantryTests
    {
        static GameData data;
        static GameData Data => data ??= GameData.Parse(File.ReadAllText("Assets/Resources/GameData.json"));

        static Ingredient Ing(string id) => Data.Ingredients[id];
        static Recipe Dish(string id) => Data.Recipes.First(r => r.Id == id);

        [Test]
        public void MarketDataLoads()
        {
            Assert.AreEqual("面米铺", Ing("flour").Vendor);
            Assert.AreEqual(300, Ing("flour").PremiumCost);           // 优质贵一半
            Assert.AreEqual(0.2, Ing("greens").BadRate, 1e-9);
            Assert.AreEqual(0.06, Ing("greens").BadRatePremium, 1e-9);
            Assert.AreEqual(0.3, Ing("greens").OvernightBad, 1e-9);
            Assert.IsTrue(Ing("pork").IsMain);
            Assert.IsFalse(Ing("salt").IsMain);
            Assert.IsFalse(Ing("salt").HasPremium);
            Assert.AreEqual(60, Data.StageFor(0).InventoryCap);
            Assert.AreEqual(320, Data.Stages.Last().InventoryCap);
            var pc = Data.Procurement;
            Assert.AreEqual(0.9, pc.Bulk[10], 1e-9);
            Assert.AreEqual(0.8, pc.Bulk[20], 1e-9);
            Assert.AreEqual(3, pc.Bargains.Count);
            Assert.AreEqual(("让一点吧", 0.05, 0.9), pc.Bargains[0]);
            Assert.AreEqual(0.05, pc.AutoInspectionMiss, 1e-9);
            Assert.AreEqual(10, pc.PremiumGoodPp, 1e-9);
        }

        [Test]
        public void PricesWithHeapAndBargain()
        {
            var p = new Pantry(Data);
            var flour = Ing("flour");
            Assert.AreEqual(200, p.UnitPrice(flour, Grade.Normal, 1, 0));
            Assert.AreEqual(180, p.UnitPrice(flour, Grade.Normal, 10, 0));     // 满 10 份九折
            Assert.AreEqual(160, p.UnitPrice(flour, Grade.Normal, 20, 0));     // 整筐八折
            Assert.AreEqual(144, p.UnitPrice(flour, Grade.Normal, 20, 0.1));   // 八折再砍一成：七二折
            Assert.AreEqual(140, p.UnitPrice(flour, Grade.Normal, 20, 0.2));   // 六四折低于七成：按七成
            Assert.AreEqual(300, p.UnitPrice(flour, Grade.Premium, 20, 0));    // 优质不打整筐折
            Assert.AreEqual(270, p.UnitPrice(flour, Grade.Premium, 1, 0.1));   // 只能砍价
            Assert.AreEqual(10, p.UnitPrice(Ing("salt"), Grade.Normal, 50, 0)); // 调料不打整筐折
            Assert.AreEqual(19, p.UnitPrice(Ing("oil"), Grade.Normal, 1, 0.05)); // 20 × 0.95，按记账单位向上取整
        }

        [Test]
        public void HeapsComeBadMoreOften()
        {
            var p = new Pantry(Data);
            Assert.AreEqual(0.2, p.BadRate(Ing("greens"), Grade.Normal, 9), 1e-9);
            Assert.AreEqual(0.25, p.BadRate(Ing("greens"), Grade.Normal, 10), 1e-9);   // 压在下面的容易坏
            Assert.AreEqual(0.06, p.BadRate(Ing("greens"), Grade.Premium, 20), 1e-9);
            Assert.AreEqual(0.0, p.BadRate(Ing("salt"), Grade.Normal, 50), 1e-9);
        }

        [Test]
        public void InspectionKeepsWhatIsGoodAndMissesSome()
        {
            var p = new Pantry(Data);
            var order = new[] { new OrderLine { Id = "greens", Qty = 200 }, new OrderLine { Id = "flour", Qty = 20 } };
            var got = p.Receive(order, _ => 0, 0.05, new Random(11));
            var g = got.First(a => a.Id == "greens");
            Assert.AreEqual(200, g.Bought);
            Assert.That(g.Bad, Is.InRange(30, 70));                   // a quarter of a heap of 200
            Assert.That(g.Found, Is.InRange(g.Bad - 10, g.Bad));       // most of them found
            Assert.AreEqual(g.Kept, p.Count("greens"));
            Assert.AreEqual(g.Bad - g.Found, p.Lots.First(l => l.Id == "greens").HiddenBad);
            Assert.AreEqual(220 - got.Sum(a => a.Found), p.MainCount);
            // by hand nothing is missed by chance
            var q = new Pantry(Data);
            var h = q.Receive(new[] { new OrderLine { Id = "greens", Qty = 100 } }, _ => 0, 0, new Random(3)).First();
            Assert.AreEqual(h.Bad, h.Found);
            Assert.AreEqual(0, q.Lots.Sum(l => l.HiddenBad));
        }

        [Test]
        public void TakingADishIsAllOrNothing()
        {
            var p = new Pantry(Data);
            var noodles = Dish("D02");   // 菜面: 面粉、时蔬, 盐、油、葱
            foreach (var id in new[] { "flour", "salt", "oil", "scallion" }) p.Lots.Add(new Lot { Id = id, Count = 3, UnitCost = 100 });
            Assert.IsFalse(p.Has(noodles));
            CollectionAssert.AreEqual(new[] { "greens" }, p.Short(noodles).ToArray());
            Assert.IsNull(p.Take(noodles, new Random(1)));
            Assert.AreEqual(3, p.Count("flour"));                       // nothing was taken
            p.Lots.Add(new Lot { Id = "greens", Grade = Grade.Normal, Count = 2, UnitCost = 200 });
            Assert.AreEqual(2, p.Portions(noodles));
            Assert.IsTrue(p.Has(noodles, new[] { noodles }));
            Assert.IsFalse(p.Has(noodles, new[] { noodles, noodles }));
            var t = p.Take(noodles, new Random(1));
            Assert.IsNotNull(t);
            Assert.AreEqual(2, p.Count("flour"));
            Assert.AreEqual(1, p.Count("greens"));
            Assert.AreEqual(2, p.Count("salt"));
        }

        [Test]
        public void AllPremiumMainsMakeAPremiumDish()
        {
            var p = new Pantry(Data);
            var noodles = Dish("D02");
            foreach (var id in new[] { "salt", "oil", "scallion" }) p.Lots.Add(new Lot { Id = id, Count = 5, UnitCost = 10 });
            p.Lots.Add(new Lot { Id = "flour", Grade = Grade.Normal, Count = 5, UnitCost = 200 });
            p.Lots.Add(new Lot { Id = "flour", Grade = Grade.Premium, Count = 1, UnitCost = 300 });
            p.Lots.Add(new Lot { Id = "greens", Grade = Grade.Premium, Count = 1, UnitCost = 300 });
            p.Lots.Add(new Lot { Id = "greens", Grade = Grade.Normal, Count = 5, UnitCost = 200 });
            var first = p.Take(noodles, new Random(1));
            Assert.IsTrue(first.Premium);                               // the 优质 there is goes first, together
            Assert.AreEqual(0, p.Count("flour", Grade.Premium));
            var second = p.Take(noodles, new Random(1));
            Assert.IsFalse(second.Premium);
        }

        [Test]
        public void AMissedBadPortionIsFoundInTheDish()
        {
            var p = new Pantry(Data);
            foreach (var id in new[] { "salt", "oil" }) p.Lots.Add(new Lot { Id = id, Count = 5, UnitCost = 10 });
            p.Lots.Add(new Lot { Id = "flour", Count = 2, HiddenBad = 2, UnitCost = 200 });
            var t = p.Take(Dish("D01"), new Random(1));                 // 胡饼: 面粉, 盐、油
            Assert.IsTrue(t.Bad);
            Assert.AreEqual(1, p.Lots.First(l => l.Id == "flour").HiddenBad);
        }

        [Test]
        public void OvernightSpoilsByKind()
        {
            var p = new Pantry(Data);
            p.Lots.Add(new Lot { Id = "flour", Count = 100, UnitCost = 200 });    // 面米不坏
            p.Lots.Add(new Lot { Id = "greens", Count = 100, UnitCost = 200 });   // 蔬菜 30%
            p.Lots.Add(new Lot { Id = "pork", Count = 100, UnitCost = 500 });     // 肉 20%
            p.Lots.Add(new Lot { Id = "salt", Count = 100, UnitCost = 10 });      // 调料不坏
            var gone = p.Overnight(new Random(5));
            Assert.IsFalse(gone.ContainsKey("flour"));
            Assert.IsFalse(gone.ContainsKey("salt"));
            Assert.That(gone["greens"], Is.InRange(18, 42));
            Assert.That(gone["pork"], Is.InRange(10, 30));
            Assert.AreEqual(100 - gone["greens"], p.Count("greens"));
            Assert.AreEqual(100, p.Count("flour"));
        }

        [Test]
        public void EachVendorCanBeAskedOnceADay()
        {
            var m = new MarketDay();
            var rules = Data.Procurement;
            var rng = new Random(2);
            bool first = m.Bargain("面米铺", 0, rules, rng);
            Assert.IsTrue(m.Asked("面米铺"));
            Assert.AreEqual(first ? 0.05 : 0, m.Discount("面米铺"), 1e-9);
            Assert.IsFalse(m.Bargain("面米铺", 2, rules, rng));          // not twice
            Assert.AreEqual(first ? 0.05 : 0, m.Discount("面米铺"), 1e-9);
            Assert.AreEqual(0, m.Discount("肉铺"), 1e-9);
            m.NextDay();
            Assert.IsFalse(m.Asked("面米铺"));
            Assert.AreEqual(0, m.Discount("面米铺"), 1e-9);
            // over many vendors the odds hold: "让一点吧" nine in ten
            int ok = Enumerable.Range(0, 400).Count(k => m.Bargain("v" + k, 0, rules, rng));
            Assert.That(ok, Is.InRange(340, 390));
        }

        [Test]
        public void GuestsOnlyOrderWhatCanBeMade()
        {
            // 胡饼 can be made, nothing else: everyone orders 胡饼; with nothing at all they walk out
            var menu = Data.Recipes.Where(r => r.IsOpen(0, new string[0])).ToList();
            var p = new Pantry(Data);
            foreach (var id in new[] { "flour", "salt", "oil" }) p.Lots.Add(new Lot { Id = id, Count = 100, UnitCost = 100 });
            var s = new Service(Data, new Random(9)) { CanOffer = (r, before) => p.Has(r, before) };
            s.StartDay(0, Data.StageFor(0), 1, menu, 1.0);
            s.Tick(4_000, true);
            Assert.AreEqual(1, s.Parties.Count);
            Assert.IsTrue(s.Parties[0].Plates.All(pl => pl.Dish.Id == "D01"));
            var empty = new Pantry(Data);
            var s2 = new Service(Data, new Random(9)) { CanOffer = (r, before) => empty.Has(r, before) };
            s2.StartDay(0, Data.StageFor(0), 1, menu, 1.0);
            s2.Tick(4_000, true);
            Assert.AreEqual(0, s2.Parties.Count);
            Assert.That(s2.GuestsLeft, Is.GreaterThan(0));
            Assert.AreEqual(s2.GuestsArrived, s2.GuestsLeft);
        }

        [Test]
        public void PremiumDishesAreLikedBetter()
        {
            // the same table served 完美 twice, once plain and once 优质: over many tables more 好评 with 优质
            int Good(bool premium)
            {
                int good = 0;
                for (int seed = 0; seed < 300; seed++)
                {
                    var s = new Service(Data, new Random(seed));
                    s.StartDay(0, Data.StageFor(0), 1, Data.Recipes.Where(r => r.IsOpen(0, new string[0])), 1.0);
                    s.Tick(4_000, true);
                    foreach (var (party, plate) in s.Pending().ToList()) s.Serve(party, plate, Quality.Perfect, 5_000, premium);
                    s.Tick(5_000 + 30_000, true);
                    good += s.Good;
                }
                return good;
            }
            Assert.Greater(Good(true), Good(false));
        }
    }
}
