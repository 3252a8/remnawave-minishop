type SendTypingSignal = (ticketId: number, typing: boolean) => void | Promise<unknown>;

type SupportTypingHeartbeatOptions = {
  send: SendTypingSignal;
  heartbeatMs?: number;
  idleMs?: number;
};

export function createSupportTypingHeartbeat({
  send,
  heartbeatMs = 4_000,
  idleMs = 6_000,
}: SupportTypingHeartbeatOptions) {
  let activeTicketId: number | null = null;
  let heartbeatTimer: ReturnType<typeof globalThis.setInterval> | null = null;
  let idleTimer: ReturnType<typeof globalThis.setTimeout> | null = null;
  let requestQueue: Promise<unknown> = Promise.resolve();

  function enqueue(ticketId: number, typing: boolean): void {
    requestQueue = requestQueue.then(() => send(ticketId, typing)).catch(() => undefined);
  }

  function clearTimers(): void {
    if (heartbeatTimer !== null) globalThis.clearInterval(heartbeatTimer);
    if (idleTimer !== null) globalThis.clearTimeout(idleTimer);
    heartbeatTimer = null;
    idleTimer = null;
  }

  function stop(expectedTicketId?: number): void {
    if (activeTicketId === null) return;
    if (expectedTicketId && activeTicketId !== expectedTicketId) return;
    const ticketId = activeTicketId;
    activeTicketId = null;
    clearTimers();
    enqueue(ticketId, false);
  }

  function pulse(ticketId: number): void {
    const normalizedTicketId = Math.max(0, Number(ticketId) || 0);
    if (!normalizedTicketId) return;
    if (activeTicketId !== normalizedTicketId) {
      stop();
      activeTicketId = normalizedTicketId;
      enqueue(normalizedTicketId, true);
      heartbeatTimer = globalThis.setInterval(
        () => {
          if (activeTicketId === normalizedTicketId) enqueue(normalizedTicketId, true);
        },
        Math.max(1_000, heartbeatMs)
      );
    }
    if (idleTimer !== null) globalThis.clearTimeout(idleTimer);
    idleTimer = globalThis.setTimeout(() => stop(normalizedTicketId), Math.max(1_500, idleMs));
  }

  return { pulse, stop };
}
