namespace BianHe.Core
{
    public enum StoveState { Locked, Idle, Cooking, Burning }

    /// <summary>One stove (一口灶): cooks one portion at a time. Time is passed in by the caller.</summary>
    public class Stove
    {
        public StoveTier Tier;
        public bool Unlocked;
        public Recipe Dish { get; private set; }
        public long StartMs { get; private set; }
        public long BurnAtMs { get; private set; }

        /// <summary>What the dish in it took off the shelf: all its main ingredients 优质; a bad portion inspection missed
        /// (the dish is lost at 出锅). Set by whoever starts it from the storeroom.</summary>
        public bool Premium, Spoiled;

        public Stove(StoveTier tier, bool unlocked)
        {
            Tier = tier;
            Unlocked = unlocked;
        }

        public StoveState State(long nowMs)
        {
            if (!Unlocked) return StoveState.Locked;
            if (Dish == null) return StoveState.Idle;
            return nowMs <= BurnAtMs ? StoveState.Cooking : StoveState.Burning;
        }

        /// <summary>Where the needle is now, 0 … 1 (0.5 is the middle of the gold band).</summary>
        public double Needle(long nowMs) => Dish == null ? 0 : CookRules.Needle(Dish.Difficulty, nowMs - StartMs);

        /// <summary>Time left before it burns.</summary>
        public long LeftMs(long nowMs) => Dish == null ? 0 : BurnAtMs - nowMs;

        public enum StartResult { Ok, Locked, Busy, TierTooLow, Short }

        public StartResult Start(Recipe dish, long nowMs, float speedup = 0f)
        {
            if (!Unlocked) return StartResult.Locked;
            if (Dish != null) return StartResult.Busy;
            if (!CookRules.CanCook(Tier, dish.Difficulty)) return StartResult.TierTooLow;
            Dish = dish;
            StartMs = nowMs;
            BurnAtMs = CookRules.BurnAt(nowMs, dish.CookMs, speedup);
            return StartResult.Ok;
        }

        /// <summary>When the dish is done (the ready time T: its cook time after it went in; the gauge's grace runs on to
        /// BurnAtMs).</summary>
        public long ReadyMs => BurnAtMs - CookRules.GraceMs;

        /// <summary>自动做菜 at the ready time: the dish comes out as auto-cook makes it (CookRules.AutoQuality: 简单、中等
        /// 完美, 高等 不错), whatever the needle says, and the stove is free.</summary>
        public Quality AutoTakeOut()
        {
            var q = CookRules.AutoQuality(Dish.Difficulty);
            Dish = null;
            Premium = Spoiled = false;
            return q;
        }

        /// <summary>出锅: judge by where the needle is (and whether time ran out) and free the stove.</summary>
        public Quality TakeOut(long nowMs, bool byHand = true)
        {
            var q = CookRules.Judge(Dish.Difficulty, Needle(nowMs), nowMs > BurnAtMs, byHand);
            Dish = null;
            Premium = Spoiled = false;
            return q;
        }
    }
}
