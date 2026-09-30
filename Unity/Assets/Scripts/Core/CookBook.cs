using System.Collections.Generic;

namespace BianHe.Core
{
    /// <summary>
    /// 自动做菜 counters, one per dish. Counting starts at 第二关 (the 国子监 students' table);
    /// dishes cooked in 第一关 don't count, so <see cref="Counting"/> stays off until then.
    /// </summary>
    public class CookBook
    {
        public bool Counting;
        readonly Dictionary<string, int> counts = new();
        readonly HashSet<string> auto = new();

        public int Count(Recipe r) => counts.TryGetValue(r.Id, out var n) ? n : 0;
        public bool IsAuto(Recipe r) => auto.Contains(r.Id);

        /// <summary>"胡饼 2/3" style progress text.</summary>
        public string Progress(Recipe r) =>
            IsAuto(r) ? "已自动做" : $"{Count(r)}/{CookRules.AutoCookThreshold(r.Difficulty)}";

        /// <summary>Records a hand-cooked result; true when this unlocks auto-cook for the dish.</summary>
        public bool RecordHandCooked(Recipe r, Quality q)
        {
            if (!Counting || auto.Contains(r.Id) || !CookRules.CountsTowardAutoCook(r.Difficulty, q)) return false;
            int n = Count(r) + 1;
            counts[r.Id] = n;
            if (n < CookRules.AutoCookThreshold(r.Difficulty)) return false;
            auto.Add(r.Id);
            return true;
        }

        /// <summary>The player can switch auto-cook off (and back on) per dish in the recipe page.</summary>
        public void SetAuto(Recipe r, bool on)
        {
            if (on && Count(r) >= CookRules.AutoCookThreshold(r.Difficulty)) auto.Add(r.Id);
            else if (!on) auto.Remove(r.Id);
        }
    }
}
