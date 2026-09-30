using System;
using System.IO;
using System.Linq;
using BianHe.Core;
using NUnit.Framework;

namespace BianHe.Tests
{
    /// <summary>Guests, patience, reviews and experience against 《玩法与数值》03 and rules.service.</summary>
    public class ServiceTests
    {
        static GameData data;
        static GameData Data => data ??= GameData.Parse(File.ReadAllText("Assets/Resources/GameData.json"));

        static Service NewDay(int seed, out StageInfo stage)
        {
            var s = new Service(Data, new Random(seed));
            stage = Data.StageFor(0);
            s.StartDay(0, stage, 1, Data.Recipes.Where(r => r.IsOpen(0, new string[0])), 1.0);
            return s;
        }

        [Test]
        public void StagesAndProfilesLoad()
        {
            Assert.AreEqual("1_1", Data.StageFor(0).Id);
            Assert.AreEqual(12, Data.StageFor(0).VisitorCap);
            Assert.AreEqual(90_000, Data.StageFor(0).ArrivalIntervalMs);
            Assert.AreEqual("1_2", Data.StageFor(60).Id);
            Assert.AreEqual(60, Data.NextStage(0).Xp);
            Assert.AreEqual(22, Data.Profiles["worker"].BudgetWen);
            Assert.AreEqual("普通工人", Data.Profiles["worker"].Name);
            Assert.AreEqual(30000, Data.StartCash);
        }

        [Test]
        public void PatienceAndDining()
        {
            Assert.AreEqual(35_000, ServiceRules.PatienceMs(1, 3));   // 三位工人点简单菜：25＋5×2
            Assert.AreEqual(45_000, ServiceRules.PatienceMs(3, 1));
            Assert.AreEqual(30_000, ServiceRules.DiningMs(1));
            Assert.AreEqual(50_000, ServiceRules.DiningMs(3));
        }

        [Test]
        public void ReviewModifiersMoveBetweenColumns()
        {
            var o = ServiceRules.Modify(ServiceRules.BaseOdds(Quality.Perfect), 15);
            Assert.AreEqual(0.85, o.good, 1e-9);
            Assert.AreEqual(0.10, o.normal, 1e-9);
            Assert.AreEqual(0.05, o.bad, 1e-9);
            o = ServiceRules.Modify(ServiceRules.BaseOdds(Quality.Perfect), 30);   // 一般扣完再扣差评
            Assert.AreEqual(1.0, o.good, 1e-9);
            Assert.AreEqual(0.0, o.normal, 1e-9);
            Assert.AreEqual(0.0, o.bad, 1e-9);
            o = ServiceRules.Modify(ServiceRules.BaseOdds(Quality.Underdone), -10);  // 减下来的归到一般
            Assert.AreEqual(0.10, o.good, 1e-9);
            Assert.AreEqual(0.50, o.normal, 1e-9);
        }

        [Test]
        public void ShiftDownAndXp()
        {
            Assert.AreEqual(Review.Normal, ServiceRules.ShiftDown(Review.Good));
            Assert.AreEqual(Review.Bad, ServiceRules.ShiftDown(Review.Normal));
            Assert.AreEqual(Review.Bad, ServiceRules.ShiftDown(Review.Bad));
            // 例：8 好评＋2 一般＋2 差评＝60 经验
            Assert.AreEqual(60, 8 * ServiceRules.Xp(Review.Good) + 2 * ServiceRules.Xp(Review.Normal) + 2 * ServiceRules.Xp(Review.Bad));
        }

        [Test]
        public void WorkersLikeHotFood()
        {
            var worker = Data.Profiles["worker"];
            foreach (var r in Data.Recipes.Where(r => r.IsOpen(0, new string[0])))
                Assert.IsTrue(ServiceRules.TasteMatch(r, worker), r.Name);   // 胡饼、菜面、馄饨 are all hot
        }

        [Test]
        public void FullServiceLoop()
        {
            var s = NewDay(1, out _);
            s.Tick(3_999, true);
            Assert.AreEqual(0, s.Parties.Count);
            s.Tick(4_000, true);
            Assert.AreEqual(1, s.Parties.Count);
            var p = s.Parties[0];
            s.Tick(4_000, true);                      // seated on the next tick
            Assert.AreEqual(PartyState.Waiting, p.State);
            Assert.That(p.Guests.Count, Is.InRange(2, 4));
            Assert.IsTrue(p.Guests.All(g => g.Plates.Sum(pl => pl.Dish.Price) <= 2200), "each worker stays within 22 文");
            long t = 10_000;
            foreach (var (_, plate) in s.Pending().ToList())
                Assert.IsTrue(s.Deliver(plate.Dish, Quality.Perfect, t));
            Assert.AreEqual(PartyState.Dining, p.State);
            s.Tick(t + 29_999, true);
            Assert.AreEqual(PartyState.Dining, p.State);
            s.Tick(t + 30_000, true);
            Assert.AreEqual(PartyState.Paid, p.State);
            Assert.AreEqual(p.Plates.Sum(pl => pl.Dish.Price), s.Revenue);
            Assert.AreEqual(p.Guests.Count, s.GuestsPaid);
            Assert.AreEqual(p.Guests.Sum(g => ServiceRules.Xp(g.Review.Value)), s.Xp);
        }

        [Test]
        public void LateThenLeave()
        {
            var s = NewDay(2, out _);
            s.Tick(4_000, true);
            s.Tick(4_000, true);
            var p = s.Parties[0];
            long patience = p.PatienceMs;
            s.Tick(4_000 + patience, true);
            Assert.IsFalse(p.Late);
            s.Tick(4_000 + patience + 1, true);
            Assert.IsTrue(p.Late);                     // 催单
            s.Tick(4_000 + patience + 15_001, true);
            Assert.AreEqual(PartyState.LeftAngry, p.State);
            Assert.AreEqual(0, s.Revenue);
            Assert.AreEqual(0, s.Xp);
            Assert.AreEqual(p.Guests.Count, s.GuestsLeft);
        }

        [Test]
        public void LateReviewsShiftDown()
        {
            // 仙味 is always 好评, so a late table must get exactly 一般 from everyone
            var s = NewDay(3, out _);
            s.Tick(4_000, true);
            s.Tick(4_000, true);
            var p = s.Parties[0];
            s.Tick(4_000 + p.PatienceMs + 1, true);
            foreach (var (_, plate) in s.Pending().ToList()) s.Deliver(plate.Dish, Quality.Immortal, 45_000);
            s.Tick(45_000 + 30_000, true);
            Assert.IsTrue(p.Guests.All(g => g.Review == Review.Normal));
        }

        [Test]
        public void BurntAndUnorderedDishesAreWasted()
        {
            var s = NewDay(4, out _);
            s.Tick(4_000, true);
            s.Tick(4_000, true);
            var dish = s.Pending().First().plate.Dish;
            Assert.IsFalse(s.Deliver(dish, Quality.Burnt, 5_000));
            var other = Data.Recipes.First(r => r.Difficulty == 3);
            Assert.IsFalse(s.Deliver(other, Quality.Good, 5_000));
            Assert.AreEqual(2, s.Wasted);
        }

        [Test]
        public void SecondGroupWaitsAtDoorThenLeaves()
        {
            // a made-up fast stage so the second group arrives while the only table is taken
            var fast = new StageInfo { Id = "test", VisitorCap = 12, TableCap = 1, ArrivalIntervalMs = 5_000 };
            var s = new Service(Data, new Random(5));
            s.StartDay(0, fast, 1, Data.Recipes.Take(3), 1.0);
            long t = 4_000;
            while (s.Parties.Count < 2) { s.Tick(t, true); t += 100; }
            var p2 = s.Parties[1];
            Assert.AreEqual(PartyState.AtDoor, p2.State);
            long arrived = p2.ArrivedMs;
            s.Tick(arrived + ServiceRules.DoorWaitMs, false);
            Assert.AreEqual(PartyState.AtDoor, p2.State);
            s.Tick(arrived + ServiceRules.DoorWaitMs + 1, false);
            Assert.AreEqual(PartyState.LeftAtDoor, p2.State);   // 最多等 10 秒就走，不计经验也不算差评
            Assert.AreEqual(0, s.Bad);
        }

        [Test]
        public void DayPlanFollowsReputation()
        {
            var s = new Service(Data, new Random(6));
            s.StartDay(0, Data.StageFor(0), 1, Data.Recipes.Take(3), 0.6 + 0.4 * 0.5);
            Assert.AreEqual(9, s.Planned);            // floor(12 × 0.8)
            long t = 0;
            while (t < 600_000) { s.Tick(t, true); t += 500; }
            Assert.AreEqual(9, s.GuestsArrived);
        }
    }
}
