using System;
using System.IO;
using System.Linq;
using BianHe.Core;
using NUnit.Framework;

namespace BianHe.Tests
{
    /// <summary>Buying tables and the 二楼 against 《玩法与数值》04 桌椅与扩建 and rules.economy (as economy_sim buys them).</summary>
    public class PremisesTests
    {
        static GameData data;
        static GameData Data => data ??= GameData.Parse(File.ReadAllText("Assets/Resources/GameData.json"));

        static StageInfo Stage(string id) => Data.Stages.First(s => s.Id == id);

        /// <summary>Buys whatever is next, as GameSession does, and returns it.</summary>
        static Offer BuyNext(Premises p, string stage, int day)
        {
            var o = p.Next(Stage(stage), day);
            Assert.IsNotNull(o);
            Assert.IsTrue(o.Allowed, $"{o.Kind} {o.Table} at {stage}");
            p.Buy(o, day);
            return o;
        }

        [Test]
        public void PricesLoad()
        {
            var r = Data.Premises;
            Assert.AreEqual(6000, r.TablePrice[2]);       // 第 2 张 60 文
            Assert.AreEqual(12000, r.TablePrice[3]);
            Assert.AreEqual(25000, r.TablePrice[4]);
            Assert.AreEqual(25000, r.TablePrice[7]);      // 二楼加桌 250
            Assert.AreEqual(35000, r.TablePrice[12]);     // 第 9–12 张 350
            Assert.AreEqual(70000, r.ExpansionPrice);     // 扩建 700
            Assert.AreEqual("3", r.ExpansionMinStage);
            CollectionAssert.AreEqual(new[] { 5, 6 }, r.ExpansionTables);
            Assert.AreEqual(4, r.GroundFloorMax);
            Assert.AreEqual(12, r.MaxTables);
        }

        [Test]
        public void FirstTableComesWithTheShop()
        {
            var p = new Premises(Data);
            CollectionAssert.AreEqual(new[] { 1 }, p.OpenTables(1).ToArray());
            var o = p.Next(Stage("1_1"), 1);
            Assert.AreEqual(OfferKind.Table, o.Kind);
            Assert.AreEqual(2, o.Table);
            Assert.AreEqual(6000, o.Price);
            Assert.IsFalse(o.Allowed);                     // 一级① has room for one table
            Assert.AreEqual("1_2", o.NeedsStage.Id);
        }

        [Test]
        public void GroundFloorInOrderEachWithItsStage()
        {
            var p = new Premises(Data);
            Assert.AreEqual(2, BuyNext(p, "1_2", 3).Table);
            var o = p.Next(Stage("1_2"), 3);
            Assert.AreEqual(3, o.Table);
            Assert.IsFalse(o.Allowed);
            Assert.AreEqual("1_3", o.NeedsStage.Id);
            Assert.AreEqual(3, BuyNext(p, "1_3", 4).Table);
            Assert.AreEqual("2", p.Next(Stage("1_3"), 4).NeedsStage.Id);
            Assert.AreEqual(4, BuyNext(p, "2", 7).Table);
            CollectionAssert.AreEqual(new[] { 1, 2, 3, 4 }, p.OpenTables(7).ToArray());
        }

        [Test]
        public void ExpansionNeedsThreeAndAFullGroundFloor()
        {
            var p = new Premises(Data);
            p.Grant(3, 9);
            var o = p.Next(Stage("3"), 9);
            Assert.AreEqual(OfferKind.Table, o.Kind);      // the 一楼 is filled first (economy_sim.next_table)
            Assert.AreEqual(4, o.Table);
            p.Buy(o, 9);
            o = p.Next(Stage("2"), 9);
            Assert.AreEqual(OfferKind.Expansion, o.Kind);
            Assert.IsFalse(o.Allowed);
            Assert.AreEqual("3", o.NeedsStage.Id);
            o = p.Next(Stage("3"), 9);
            Assert.IsTrue(o.Allowed);
            Assert.AreEqual(70000, o.Price);
            CollectionAssert.AreEqual(new[] { 5, 6 }, o.Tables);
        }

        [Test]
        public void ExpansionOpensTheNextDay()
        {
            var p = new Premises(Data);
            p.Grant(4, 10);
            var o = BuyNext(p, "3", 10);
            Assert.AreEqual(OfferKind.Expansion, o.Kind);
            Assert.IsTrue(p.Expanded);
            CollectionAssert.AreEqual(new[] { 1, 2, 3, 4, 5, 6 }, p.Bought.ToArray());     // built today …
            CollectionAssert.AreEqual(new[] { 1, 2, 3, 4 }, p.OpenTables(10).ToArray());   // … nobody sits up there yet
            Assert.IsNull(p.Next(Stage("5"), 10));                                            // nothing more until it opens
            CollectionAssert.AreEqual(new[] { 1, 2, 3, 4, 5, 6 }, p.OpenTables(11).ToArray());
            o = p.Next(Stage("3"), 11);
            Assert.AreEqual(7, o.Table);
            Assert.IsFalse(o.Allowed);
            Assert.AreEqual("4", o.NeedsStage.Id);
        }

        [Test]
        public void UpstairsTablesToTwelve()
        {
            var p = new Premises(Data);
            p.Grant(6, 14);
            Assert.AreEqual(7, BuyNext(p, "4", 14).Table);
            Assert.AreEqual(8, BuyNext(p, "4", 14).Table);
            Assert.AreEqual("5", p.Next(Stage("4"), 14).NeedsStage.Id);
            var prices = Enumerable.Range(0, 4).Select(_ => BuyNext(p, "5", 16)).ToList();
            CollectionAssert.AreEqual(new[] { 9, 10, 11, 12 }, prices.Select(o => o.Table).ToArray());
            Assert.IsTrue(prices.All(o => o.Price == 35000));
            Assert.AreEqual("雅间二", p.Place(12));
            Assert.AreEqual("雅间一", p.Place(6));
            Assert.AreEqual("一楼", p.Place(4));
            Assert.AreEqual("二楼", p.Place(5));
            Assert.IsNull(p.Next(Stage("5"), 16));          // all twelve
            Assert.AreEqual(12, p.OpenTables(16).Count());
        }

        [Test]
        public void GrantedTablesAreOpenOnTheDay()
        {
            var p = new Premises(Data);
            p.Grant(8, 1);                                   // -stage 4: everything it allows, the 二楼 open on day 1
            CollectionAssert.AreEqual(Enumerable.Range(1, 8).ToArray(), p.OpenTables(1).ToArray());
            p.Grant(5, 1);                                   // the 二楼 comes as a whole: five is the 一楼's four
            CollectionAssert.AreEqual(new[] { 1, 2, 3, 4 }, p.Bought.ToArray());
            Assert.IsFalse(p.Expanded);
        }

        [Test]
        public void GuestsSitOnlyAtOpenTables()
        {
            // a made-up fast stage: three groups come in while tables 1 and 3 are open (table 2 not bought)
            var fast = new StageInfo { Id = "test", VisitorCap = 12, TableCap = 4, ArrivalIntervalMs = 2_000 };
            var s = new Service(Data, new Random(7));
            s.StartDay(0, fast, new[] { 2, 0 }, Data.Recipes.Take(3), 1.0);
            CollectionAssert.AreEqual(new[] { 0, 2 }, s.Tables.ToArray());
            long t = 4_000;
            while (s.Parties.Count < 3 && t < 60_000) { s.Tick(t, true); t += 100; }
            s.Tick(t, true);
            CollectionAssert.AreEquivalent(new[] { 0, 2 }, s.Parties.Where(p => p.Table >= 0).Select(p => p.Table).ToArray());
            var third = s.Parties[2];
            Assert.AreEqual(PartyState.AtDoor, third.State);
            s.OpenTable(1);                                  // a table bought while they wait at the door
            s.Tick(t + 100, true);
            Assert.AreEqual(PartyState.Waiting, third.State);
            Assert.AreEqual(1, third.Table);
        }
    }
}
