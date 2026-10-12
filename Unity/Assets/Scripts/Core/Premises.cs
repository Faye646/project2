using System.Collections.Generic;
using System.Linq;

namespace BianHe.Core
{
    public enum OfferKind { Table, Expansion }

    /// <summary>The next thing the shop floor can be given: a table, or the 二楼 with 雅间一.</summary>
    public class Offer
    {
        public OfferKind Kind;
        public int Table;              // the table it adds (the 二楼: its first, 第 5 张)
        public int[] Tables;           // every table it brings (the 二楼: 第 5 张 and 雅间一's 第 6 张)
        public int Price;              // 1/100 文
        public bool Allowed;           // the 声望 stage's table cap reaches it
        public StageInfo NeedsStage;   // when not: the first stage that allows it
    }

    /// <summary>
    /// The shop's tables as bought (《玩法与数值》04 桌椅与扩建, as economy_sim.next_table buys them). The first comes with
    /// the shop; the rest are bought one at a time in the design's order: 第 2–4 张 downstairs, then the 二楼 with 雅间一
    /// (第 5、6 张, built at once and open to guests the day after it is paid for), then 第 7–12 张 upstairs, the last of
    /// them 雅间二. Each can be bought once the 声望 stage's table cap reaches it. Pure logic: the day comes from the caller.
    /// </summary>
    public class Premises
    {
        readonly GameData data;
        readonly SortedSet<int> bought = new() { 1 };

        public Premises(GameData data) => this.data = data;

        PremisesRules Rules => data.Premises;

        /// <summary>Table numbers bought, the 二楼's two among them from the day it was paid for.</summary>
        public IReadOnlyCollection<int> Bought => bought;

        /// <summary>The day the 二楼 was paid for (-1: not yet).</summary>
        public int ExpansionDay { get; private set; } = -1;

        public bool Expanded => ExpansionDay >= 0;

        /// <summary>The 二楼 takes guests from the day after it was paid for.</summary>
        public bool ExpansionOpen(int day) => Expanded && day > ExpansionDay;

        public bool IsExpansionTable(int n) => Rules.ExpansionTables.Contains(n);

        /// <summary>The tables guests can sit at on this day, by number.</summary>
        public IEnumerable<int> OpenTables(int day) => bought.Where(n => !IsExpansionTable(n) || ExpansionOpen(day));

        /// <summary>Where table n stands: 一楼, 二楼, 雅间一 or 雅间二.</summary>
        public string Place(int n) =>
            n <= Rules.GroundFloorMax ? "一楼" : n == Rules.PrivateRoom1 ? "雅间一" : n == Rules.PrivateRoom2 ? "雅间二" : "二楼";

        /// <summary>
        /// The next purchase in the design's order, and whether the current stage allows it yet. Null once every table is
        /// bought, and while the 二楼 is being built: it opens tomorrow, and the tables after it stand up there.
        /// </summary>
        public Offer Next(StageInfo stage, int day)
        {
            var r = Rules;
            int ground = bought.Count(n => n <= r.GroundFloorMax);
            Offer o;
            if (ground < r.GroundFloorMax)
                o = Table(ground + 1);
            else if (!Expanded)
                o = new Offer { Kind = OfferKind.Expansion, Table = r.ExpansionTables.Min(), Tables = r.ExpansionTables.ToArray(), Price = r.ExpansionPrice };
            else if (!ExpansionOpen(day))
                return null;
            else
            {
                int n = Enumerable.Range(1, r.MaxTables).FirstOrDefault(k => !bought.Contains(k));
                if (n == 0) return null;
                o = Table(n);
            }
            // allowed once the stage's cap reaches the tables it makes (the 二楼 also waits for its own stage)
            int count = bought.Count + o.Tables.Length;
            int minStage = o.Kind == OfferKind.Expansion ? data.StageIndex(r.ExpansionMinStage) : 0;
            bool Allows(StageInfo s) => s.TableCap >= count && data.Stages.IndexOf(s) >= minStage;
            o.Allowed = Allows(stage);
            if (!o.Allowed) o.NeedsStage = data.Stages.FirstOrDefault(Allows);
            return o;
        }

        Offer Table(int n) => new()
        {
            Kind = OfferKind.Table, Table = n, Tables = new[] { n },
            Price = Rules.TablePrice.TryGetValue(n, out var p) ? p : 0,
        };

        /// <summary>Takes it (the caller pays): a table stands at once; the 二楼 and 雅间一 are built today and open tomorrow.</summary>
        public void Buy(Offer o, int day)
        {
            foreach (var n in o.Tables) bought.Add(n);
            if (o.Kind == OfferKind.Expansion) ExpansionDay = day;
        }

        /// <summary>
        /// For starting further on (the -stage and -own switches): the first `count` tables in the order they are bought,
        /// as if bought on earlier days, so that the 二楼 among them is open on `day`.
        /// </summary>
        public void Grant(int count, int day)
        {
            var r = Rules;
            bought.Clear();
            ExpansionDay = -1;
            for (int n = 1; n <= System.Math.Max(1, System.Math.Min(count, r.GroundFloorMax)); n++) bought.Add(n);
            if (count < r.GroundFloorMax + r.ExpansionTables.Length) return;
            foreach (var n in r.ExpansionTables) bought.Add(n);
            ExpansionDay = day - 1;
            for (int n = 1; n <= r.MaxTables && bought.Count < count; n++) bought.Add(n);
        }
    }
}
