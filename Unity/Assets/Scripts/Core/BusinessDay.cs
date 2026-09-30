using System;
using System.Collections.Generic;

namespace BianHe.Core
{
    public enum DayPhase { BeforeOpening, Service, Settlement }

    /// <summary>
    /// 营业日: 开门前 (untimed) → 营业 (6 minutes; after that no new guests, seated ones are still
    /// served) → 打烊结算 (untimed) → the next day's 开门前. Closing early is allowed (e.g. out of
    /// ingredients). Time is passed in by the caller.
    /// </summary>
    public class BusinessDay
    {
        public const long ServiceMs = 6 * 60 * 1000;

        public int Day { get; private set; } = 1;
        public DayPhase Phase { get; private set; } = DayPhase.BeforeOpening;
        public long OpenedAtMs { get; private set; }
        public bool ClosedEarly { get; private set; }

        /// <summary>Dishes taken out today, by quality.</summary>
        public readonly Dictionary<Quality, int> Served = new();

        public event Action<DayPhase> PhaseChanged;

        public long RemainingMs(long nowMs) =>
            Phase == DayPhase.Service ? Math.Max(0, OpenedAtMs + ServiceMs - nowMs) : 0;

        /// <summary>New guests may still arrive.</summary>
        public bool DoorOpen(long nowMs) => Phase == DayPhase.Service && RemainingMs(nowMs) > 0;

        public void Open(long nowMs)
        {
            if (Phase != DayPhase.BeforeOpening) throw new InvalidOperationException("can only open before opening");
            OpenedAtMs = nowMs;
            ClosedEarly = false;
            Served.Clear();
            doorWasOpen = true;
            Set(DayPhase.Service);
        }

        /// <summary>Call every frame. Returns true when the service time ran out and the door just shut.
        /// Settlement itself waits for <see cref="Close"/>, once the seated guests are done.</summary>
        public bool Tick(long nowMs)
        {
            bool open = DoorOpen(nowMs);
            bool shut = doorWasOpen && !open && Phase == DayPhase.Service;
            doorWasOpen = open;
            return shut;
        }

        bool doorWasOpen;

        public void Close(long nowMs)
        {
            if (Phase != DayPhase.Service) throw new InvalidOperationException("not in service");
            ClosedEarly = RemainingMs(nowMs) > 0;
            Set(DayPhase.Settlement);
        }

        public void NextDay()
        {
            if (Phase != DayPhase.Settlement) throw new InvalidOperationException("settle first");
            Day++;
            Set(DayPhase.BeforeOpening);
        }

        public void RecordServed(Quality q) => Served[q] = (Served.TryGetValue(q, out var n) ? n : 0) + 1;

        void Set(DayPhase p)
        {
            Phase = p;
            PhaseChanged?.Invoke(p);
        }
    }
}
