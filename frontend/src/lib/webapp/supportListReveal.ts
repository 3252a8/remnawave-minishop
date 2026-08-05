/**
 * Decides what the support ticket list shows while its request is in flight.
 *
 * Skeletons are a promise that content is coming. Showing them to the majority of users, whose
 * inbox is empty, breaks that promise twice: once when they appear and once when they collapse
 * into an empty state. Three rules follow:
 *
 * - a filter already known to hold no tickets skips straight to its empty state;
 * - every other filter stays quiet until the request is slow enough to be worth explaining, so a
 *   normal response paints content without a skeleton frame in between;
 * - a skeleton that does appear is sized to the count we expect and stays long enough to read.
 */

export type SupportListPhase = "pending" | "skeleton" | "content";

export type SupportListRevealState = {
  phase: SupportListPhase;
  skeletonCount: number;
};

export type SupportListRevealInput = {
  /** Cards the active filter is expected to render; `null` when nothing is known yet. */
  expectedCount: number | null;
  /** The store holds a list that belongs to the active filter. */
  resolved: boolean;
};

export type SupportListRevealOptions = {
  defaultSkeletonCount?: number;
  failsafeMs?: number;
  maxSkeletonCount?: number;
  minSkeletonMs?: number;
  now?: () => number;
  onChange?: (state: SupportListRevealState) => void;
  probeDelayMs?: number;
};

const IDLE_STATE: SupportListRevealState = { phase: "pending", skeletonCount: 0 };

export function createSupportListReveal({
  defaultSkeletonCount = 3,
  failsafeMs = 8_000,
  maxSkeletonCount = 5,
  minSkeletonMs = 320,
  now = () => Date.now(),
  onChange = () => {},
  probeDelayMs = 220,
}: SupportListRevealOptions = {}) {
  let state: SupportListRevealState = IDLE_STATE;
  let skeletonShownAt = 0;
  let probeDeadline: number | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;

  function clearTimer() {
    if (timer === null) return;
    clearTimeout(timer);
    timer = null;
  }

  function schedule(delayMs: number, run: () => void) {
    clearTimer();
    timer = setTimeout(
      () => {
        timer = null;
        run();
      },
      Math.max(0, delayMs)
    );
  }

  function setPhase(phase: SupportListPhase, skeletonCount: number) {
    if (state.phase === phase && state.skeletonCount === skeletonCount) return state;
    if (phase === "skeleton" && state.phase !== "skeleton") skeletonShownAt = now();
    state = { phase, skeletonCount };
    onChange(state);
    return state;
  }

  function clampSkeletonCount(count: number) {
    return Math.min(maxSkeletonCount, Math.max(1, Math.floor(count)));
  }

  // A request that never resolves (offline, 5xx) must not strand the user on skeletons; the empty
  // state at least carries the "create a ticket" call to action.
  function armFailsafe() {
    schedule(failsafeMs, () => setPhase("content", 0));
  }

  function showSkeleton(count: number) {
    probeDeadline = null;
    setPhase("skeleton", clampSkeletonCount(count));
    armFailsafe();
  }

  function revealContent() {
    if (state.phase !== "skeleton") return setPhase("content", 0);
    const remaining = minSkeletonMs - (now() - skeletonShownAt);
    if (remaining <= 0) return setPhase("content", 0);
    schedule(remaining, () => setPhase("content", 0));
    return state;
  }

  function sync(input: SupportListRevealInput): SupportListRevealState {
    clearTimer();
    const expected = input.expectedCount;
    // Known-empty short-circuits: the empty state is the real answer for this filter, so there is
    // nothing a skeleton could honestly stand in for.
    if (input.resolved || expected === 0) {
      probeDeadline = null;
      return revealContent();
    }
    if (state.phase === "skeleton") {
      // Already committed: resize rather than flicker back to a blank slot.
      if (expected !== null && Number.isFinite(expected)) {
        setPhase("skeleton", clampSkeletonCount(expected));
      }
      armFailsafe();
      return state;
    }

    const count = expected === null || !Number.isFinite(expected) ? defaultSkeletonCount : expected;
    // The deadline is set once per wait, so a count arriving mid-flight resizes the skeletons
    // without pushing back — or restarting — the moment they are due.
    if (probeDeadline === null) probeDeadline = now() + probeDelayMs;
    setPhase("pending", 0);
    schedule(probeDeadline - now(), () => showSkeleton(count));
    return state;
  }

  function destroy() {
    clearTimer();
  }

  return {
    destroy,
    get state() {
      return state;
    },
    sync,
  };
}
