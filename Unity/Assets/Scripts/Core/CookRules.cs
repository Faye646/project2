using System;

namespace BianHe.Core
{
    /// <summary>出品: what comes out of the wok.</summary>
    public enum Quality { Underdone, Good, Perfect, Immortal, Burnt }

    /// <summary>灶台三档; a stove cooks dishes whose difficulty is at most its tier.</summary>
    public enum StoveTier { Basic = 1, Medium = 2, Advanced = 3 }

    /// <summary>
    /// 出锅 rules (the user's swinging-needle version of 《玩法与数值》02):
    ///   Once the dish is in the wok, a needle swings back and forth over the 火候 gauge, and the
    ///   gauge has a gold band in the middle. The dish has a time limit, 出锅时限 =
    ///   基础时长 × (1 − 仙家密法加速) + 3 s.
    ///   Within the limit: needle inside the gold band → 完美 (高等菜: 不错, or 仙味 in the band's
    ///   centre when cooked by hand); needle anywhere else → 次等 (没熟).
    ///   After the limit → 糊菜, wherever the needle is.
    /// Harder dishes swing faster and have a narrower band. Time is in whole milliseconds.
    /// </summary>
    public static class CookRules
    {
        public const int GraceMs = 3000;      // added to the recipe's cook time to make the time limit
        public const int MaxAutoStoves = 2;

        /// <summary>When the dish burns: start + base time × (1 − speed-up) + 3 s.</summary>
        public static long BurnAt(long startMs, int baseMs, float speedup = 0f)
        {
            if (speedup < 0f || speedup >= 1f) throw new ArgumentOutOfRangeException(nameof(speedup));
            return startMs + (long)Math.Round(baseMs * (1.0 - speedup)) + GraceMs;
        }

        /// <summary>One full swing, left → right → left.</summary>
        public static int SwingPeriodMs(int difficulty) => difficulty switch { 1 => 1600, 2 => 1300, _ => 1000 };

        /// <summary>Half the width of the gold band, as a fraction of the gauge (the band is centred on 0.5).</summary>
        public static double GoldHalfWidth(int difficulty) => difficulty switch { 1 => 0.11, 2 => 0.085, _ => 0.065 };

        /// <summary>Half the width of the 仙味 core inside the gold band (高等菜 only).</summary>
        public const double ImmortalHalfWidth = 0.022;

        /// <summary>Needle position 0 (left end) … 1 (right end) this long after the dish went in; starts on the left.</summary>
        public static double Needle(int difficulty, long elapsedMs)
        {
            int period = SwingPeriodMs(difficulty);
            double phase = (Math.Max(0, elapsedMs) % period) / (double)period;
            return phase < 0.5 ? phase * 2 : 2 - phase * 2;
        }

        public static bool InGold(int difficulty, double needle) => Math.Abs(needle - 0.5) <= GoldHalfWidth(difficulty) + 1e-9;

        public static Quality Judge(int difficulty, double needle, bool late, bool byHand = true)
        {
            if (late) return Quality.Burnt;
            double d = Math.Abs(needle - 0.5);
            if (d > GoldHalfWidth(difficulty) + 1e-9) return Quality.Underdone;
            if (difficulty < 3) return Quality.Perfect;
            return byHand && d <= ImmortalHalfWidth + 1e-9 ? Quality.Immortal : Quality.Good;
        }

        public static bool CanCook(StoveTier tier, int difficulty) => (int)tier >= difficulty;

        /// <summary>What auto-cook serves: simple and medium dishes come out 完美, advanced 不错.</summary>
        public static Quality AutoQuality(int difficulty) => difficulty < 3 ? Quality.Perfect : Quality.Good;

        /// <summary>亲手做好多少次后开启自动做: 简单 3、中等 8、高等 12.</summary>
        public static int AutoCookThreshold(int difficulty) => difficulty switch { 1 => 3, 2 => 8, _ => 12 };

        /// <summary>Which hand-cooked results count: 完美 for simple/medium, 不错 or 仙味 for advanced.</summary>
        public static bool CountsTowardAutoCook(int difficulty, Quality q) =>
            difficulty < 3 ? q == Quality.Perfect : q == Quality.Good || q == Quality.Immortal;

        public static string Name(Quality q) => q switch
        {
            Quality.Underdone => "没熟",
            Quality.Good => "不错",
            Quality.Perfect => "完美",
            Quality.Immortal => "仙味",
            _ => "糊了",
        };

        public static string Name(StoveTier t) => t switch
        {
            StoveTier.Basic => "初等灶台",
            StoveTier.Medium => "中等灶台",
            _ => "高等灶台",
        };

        /// <summary>Seconds with one decimal, never showing "-0.0".</summary>
        public static string Seconds(long ms) => (Math.Max(0, ms) / 1000.0).ToString("0.0");
    }
}
