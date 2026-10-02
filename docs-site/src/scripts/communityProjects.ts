for (const button of document.querySelectorAll<HTMLButtonElement>('[data-project-dialog]')) {
  const dialog = document.getElementById(button.dataset.projectDialog ?? '');
  if (!(dialog instanceof HTMLDialogElement)) continue;

  button.addEventListener('click', () => dialog.showModal());
  dialog.querySelector<HTMLButtonElement>('[data-close-project]')?.addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', (event) => {
    if (event.target !== dialog) return;
    const bounds = dialog.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) {
      dialog.close();
    }
  });
}

interface StarCache {
  count: number;
  updatedAt: number;
}

function isStarCache(value: unknown): value is StarCache {
  return typeof value === 'object' && value !== null &&
    'count' in value && typeof value.count === 'number' && Number.isInteger(value.count) && value.count >= 0 &&
    'updatedAt' in value && typeof value.updatedAt === 'number';
}

const groups = new Map<string, HTMLAnchorElement[]>();
for (const badge of document.querySelectorAll<HTMLAnchorElement>('[data-stars-api]')) {
  const api = badge.dataset.starsApi;
  if (!api) continue;
  const badges = groups.get(api) ?? [];
  badges.push(badge);
  groups.set(api, badges);
}

function updateBadges(badges: HTMLAnchorElement[], count: number, status: 'live' | 'cached') {
  for (const badge of badges) {
    const label = `Звёзды на ${badge.dataset.forge}: ${count}`;
    const countElement = badge.querySelector<HTMLElement>('[data-star-count]');
    if (countElement) countElement.textContent = new Intl.NumberFormat('ru').format(count);
    badge.setAttribute('aria-label', label);
    badge.title = label;
    badge.dataset.starsStatus = status;
  }
}

const cacheLifetime = 6 * 60 * 60 * 1000;

async function refreshStars(api: string, badges: HTMLAnchorElement[]) {
  const cacheKey = `minishop-community-stars:${api}`;
  try {
    const value: unknown = JSON.parse(localStorage.getItem(cacheKey) ?? 'null');
    if (isStarCache(value) && Date.now() - value.updatedAt < cacheLifetime) {
      updateBadges(badges, value.count, 'cached');
      return;
    }
  } catch {
    // Storage can be disabled; the catalog still works without a cache.
  }

  try {
    const response = await fetch(api, { credentials: 'omit', signal: AbortSignal.timeout(6000) });
    if (!response.ok) return;
    const data: unknown = await response.json();
    const field = badges[0]?.dataset.starsField;
    if (!field || typeof data !== 'object' || data === null || !(field in data)) return;
    const count: unknown = (data as Record<string, unknown>)[field];
    if (typeof count !== 'number' || !Number.isInteger(count) || count < 0) return;
    updateBadges(badges, count, 'live');
    try {
      localStorage.setItem(cacheKey, JSON.stringify({ count, updatedAt: Date.now() }));
    } catch {
      // Keep the refreshed value even if it cannot be cached.
    }
  } catch {
    // Offline or rate-limited APIs leave the dated public snapshot visible.
  }
}

for (const [api, badges] of groups) void refreshStars(api, badges);
