using System.IO;
using System.Linq;
using BianHe.Core;
using NUnit.Framework;

namespace BianHe.Tests
{
    /// <summary>Checks the rules in 《玩法与数值》02 (做菜与出炉) and 01 (营业日) against the code.</summary>
    public class CookingRulesTests
    {
        static Recipe Dish(int difficulty, int ms = 3000) => new Recipe
        {
            Id = "T" + difficulty, Name = "测试菜", Difficulty = difficulty, CookMs = ms,
            StoveTier = (StoveTier)difficulty, RequiredFlags = new string[0],
        };

        // ---------------------------------------------------------------- 出锅判定 (swinging needle)

        [TestCase(1, 0.5, false, Quality.Perfect)]
        [TestCase(1, 0.61, false, Quality.Perfect)]      // edge of the gold band (±0.11)
        [TestCase(1, 0.62, false, Quality.Underdone)]    // 没熟
        [TestCase(1, 0.0, false, Quality.Underdone)]
        [TestCase(1, 0.5, true, Quality.Burnt)]          // past the time limit: 糊, even in the gold
        [TestCase(1, 0.1, true, Quality.Burnt)]
        [TestCase(2, 0.58, false, Quality.Perfect)]
        [TestCase(2, 0.59, false, Quality.Underdone)]    // medium band is narrower (±0.085)
        [TestCase(3, 0.5, false, Quality.Immortal)]      // 仙味 core ±0.022
        [TestCase(3, 0.53, false, Quality.Good)]
        [TestCase(3, 0.57, false, Quality.Underdone)]
        [TestCase(3, 0.5, true, Quality.Burnt)]
        public void JudgeByHand(int difficulty, double needle, bool late, Quality expected)
        {
            Assert.AreEqual(expected, CookRules.Judge(difficulty, needle, late, byHand: true));
        }

        [Test]
        public void ImmortalOnlyByHand()
        {
            Assert.AreEqual(Quality.Good, CookRules.Judge(3, 0.5, false, byHand: false));
            Assert.AreEqual(Quality.Perfect, CookRules.AutoQuality(1));
            Assert.AreEqual(Quality.Perfect, CookRules.AutoQuality(2));
            Assert.AreEqual(Quality.Good, CookRules.AutoQuality(3));
        }

        [Test]
        public void NeedleSwingsBackAndForth()
        {
            Assert.AreEqual(0.0, CookRules.Needle(1, 0), 1e-9);        // starts on the left
            Assert.AreEqual(0.5, CookRules.Needle(1, 400), 1e-9);      // a quarter of the 1.6 s swing
            Assert.AreEqual(1.0, CookRules.Needle(1, 800), 1e-9);      // right end
            Assert.AreEqual(0.5, CookRules.Needle(1, 1200), 1e-9);     // on its way back
            Assert.AreEqual(0.0, CookRules.Needle(1, 1600), 1e-9);
            Assert.Less(CookRules.SwingPeriodMs(3), CookRules.SwingPeriodMs(1));   // harder dishes swing faster
            Assert.Less(CookRules.GoldHalfWidth(3), CookRules.GoldHalfWidth(1));   // … with a narrower band
        }

        [Test]
        public void TimeLimitIsCookTimePlusThreeSeconds()
        {
            Assert.AreEqual(1000 + 3000 + 3000, CookRules.BurnAt(1000, 3000));
            Assert.AreEqual(1000 + 8400 + 3000, CookRules.BurnAt(1000, 12000, 0.3f));   // 仙家密法 shortens the cook part
        }

        [Test]
        public void SecondsShowOneDecimal()
        {
            Assert.AreEqual("2.3", CookRules.Seconds(2345));
            Assert.AreEqual("0.0", CookRules.Seconds(-40));
        }

        // ---------------------------------------------------------------- 灶台

        [Test]
        public void StoveTierLimitsDishes()
        {
            Assert.IsTrue(CookRules.CanCook(StoveTier.Basic, 1));
            Assert.IsFalse(CookRules.CanCook(StoveTier.Basic, 2));
            Assert.IsTrue(CookRules.CanCook(StoveTier.Medium, 2));
            Assert.IsFalse(CookRules.CanCook(StoveTier.Medium, 3));
            Assert.IsTrue(CookRules.CanCook(StoveTier.Advanced, 3));
            Assert.AreEqual(Stove.StartResult.TierTooLow, new Stove(StoveTier.Basic, true).Start(Dish(2), 0));
        }

        [Test]
        public void StoveLifecycle()
        {
            var s = new Stove(StoveTier.Basic, true);
            Assert.AreEqual(StoveState.Idle, s.State(0));
            Assert.AreEqual(Stove.StartResult.Ok, s.Start(Dish(1), 1000));
            Assert.AreEqual(Stove.StartResult.Busy, s.Start(Dish(1), 1000));   // one portion at a time
            Assert.AreEqual(StoveState.Cooking, s.State(7000));                 // limit = 3 s + 3 s
            Assert.AreEqual(StoveState.Burning, s.State(7001));
            Assert.AreEqual(Quality.Perfect, s.TakeOut(1000 + 400));            // needle mid-swing, in the gold
            Assert.AreEqual(StoveState.Idle, s.State(1400));
            s.Start(Dish(1), 0);
            Assert.AreEqual(Quality.Underdone, s.TakeOut(800));                 // needle at the right end
            s.Start(Dish(1), 0);
            Assert.AreEqual(Quality.Burnt, s.TakeOut(6000 + 1600 * 3 + 400));   // in the gold but too late
        }

        [Test]
        public void LockedStoveRefuses()
        {
            var s = new Stove(StoveTier.Basic, false);
            Assert.AreEqual(StoveState.Locked, s.State(0));
            Assert.AreEqual(Stove.StartResult.Locked, s.Start(Dish(1), 0));
        }

        // ---------------------------------------------------------------- 自动做菜

        [Test]
        public void FirstStageDoesNotCount()
        {
            var book = new CookBook { Counting = false };
            var d = Dish(1);
            for (int i = 0; i < 5; i++) book.RecordHandCooked(d, Quality.Perfect);
            Assert.AreEqual(0, book.Count(d));
            Assert.IsFalse(book.IsAuto(d));
        }

        [TestCase(1, 3)]
        [TestCase(2, 8)]
        [TestCase(3, 12)]
        public void AutoCookUnlocksAtThreshold(int difficulty, int needed)
        {
            var book = new CookBook { Counting = true };
            var d = Dish(difficulty);
            var q = difficulty < 3 ? Quality.Perfect : Quality.Good;
            for (int i = 1; i < needed; i++) Assert.IsFalse(book.RecordHandCooked(d, q));
            Assert.IsTrue(book.RecordHandCooked(d, q));
            Assert.IsTrue(book.IsAuto(d));
            Assert.AreEqual("已自动做", book.Progress(d));
        }

        [Test]
        public void OnlyQualifyingResultsCount()
        {
            var book = new CookBook { Counting = true };
            var simple = Dish(1);
            book.RecordHandCooked(simple, Quality.Underdone);
            book.RecordHandCooked(simple, Quality.Burnt);
            Assert.AreEqual("0/3", book.Progress(simple));
            var adv = Dish(3);
            book.RecordHandCooked(adv, Quality.Immortal);
            book.RecordHandCooked(adv, Quality.Good);
            book.RecordHandCooked(adv, Quality.Perfect);   // advanced dishes never come out 完美
            Assert.AreEqual(2, book.Count(adv));
        }

        // ---------------------------------------------------------------- 营业日

        [Test]
        public void BusinessDayCycle()
        {
            var day = new BusinessDay();
            Assert.AreEqual(DayPhase.BeforeOpening, day.Phase);
            day.Open(1000);
            Assert.IsTrue(day.DoorOpen(1000));
            Assert.AreEqual(BusinessDay.ServiceMs, day.RemainingMs(1000));
            Assert.IsFalse(day.Tick(1000 + BusinessDay.ServiceMs - 1));
            Assert.IsTrue(day.Tick(1000 + BusinessDay.ServiceMs));     // door shuts once, at 6:00
            Assert.IsFalse(day.Tick(1000 + BusinessDay.ServiceMs + 5));
            Assert.AreEqual(DayPhase.Service, day.Phase);             // seated guests are still served
            day.RecordServed(Quality.Perfect);
            day.Close(1000 + BusinessDay.ServiceMs + 20_000);
            Assert.IsFalse(day.ClosedEarly);
            Assert.AreEqual(1, day.Served[Quality.Perfect]);
            day.NextDay();
            Assert.AreEqual(2, day.Day);
            Assert.AreEqual(DayPhase.BeforeOpening, day.Phase);
        }

        [Test]
        public void ClosingEarlyIsAllowed()
        {
            var day = new BusinessDay();
            day.Open(0);
            day.Close(60_000);
            Assert.IsTrue(day.ClosedEarly);
        }

        // ---------------------------------------------------------------- 数据

        [Test]
        public void GameDataMatchesDesign()
        {
            var data = GameData.Parse(File.ReadAllText("Assets/Resources/GameData.json"));
            Assert.AreEqual("1.3", data.SchemaVersion);
            Assert.AreEqual(23, data.Recipes.Count);
            var open = data.Recipes.Where(r => r.IsOpen(0, new string[0])).Select(r => r.Name).ToArray();
            CollectionAssert.AreEqual(new[] { "胡饼", "菜面", "馄饨" }, open);
            foreach (var r in data.Recipes)
            {
                Assert.AreEqual(r.Difficulty, (int)r.StoveTier, r.Name);
                foreach (var ing in r.Ingredients.Keys)
                    Assert.IsTrue(data.Ingredients.ContainsKey(ing), $"{r.Name} uses unknown ingredient {ing}");
            }
            var hubing = data.Recipes.First(r => r.Id == "D01");
            Assert.AreEqual(3000, hubing.CookMs);
            Assert.AreEqual("面粉", data.IngredientList(hubing));
        }
    }
}
