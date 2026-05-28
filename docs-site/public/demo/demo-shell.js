const frame = document.getElementById("demo-frame");
const runtimeBase = "/demo/runtime";
const demoBase = "/demo";
const defaultMock = "tariffs";
const publicRouteAliases = new Map([["/app", "/home"]]);
const stateMocks = new Set([
  "tariffs",
  "depleted",
  "no-subscription",
  "trial",
  "devices",
  "auth",
]);
const routeMocks = new Set([...stateMocks, "guides", "install"]);
const params = new URLSearchParams(window.location.search);

const normalizePath = (value) => {
  const raw = String(value || "").trim();
  if (!raw) return "/home";
  const withSlash = raw.startsWith("/") ? raw : `/${raw}`;
  return withSlash.replace(/\/{2,}/g, "/").replace(/\/+$/, "") || "/home";
};

const normalizeRouteMock = (value) => {
  const mock = String(value || "")
    .trim()
    .toLowerCase();
  return routeMocks.has(mock) ? mock : defaultMock;
};

const normalizeStateMock = (value) => {
  const mock = normalizeRouteMock(value);
  return stateMocks.has(mock) ? mock : defaultMock;
};

const routeFromPublicPath = () => {
  const pathname = window.location.pathname.replace(/\/+$/, "") || "/";
  const lowerPathname = pathname.toLowerCase();
  if (lowerPathname === demoBase) return "";
  if (!lowerPathname.startsWith(`${demoBase}/`)) return "";

  const publicRoute = pathname.slice(demoBase.length);
  if (!publicRoute || publicRoute.toLowerCase().startsWith("/runtime"))
    return "";
  const normalized = normalizePath(publicRoute);
  return publicRouteAliases.get(normalized.toLowerCase()) || normalized;
};

const routeFromParams = () => {
  const publicRoute = routeFromPublicPath();
  if (publicRoute) return publicRoute;

  const explicitPath = params.get("path");
  if (explicitPath) return normalizePath(explicitPath);

  const screen = String(params.get("screen") || "home")
    .trim()
    .toLowerCase();
  if (screen === "admin") {
    const adminSection = String(params.get("admin_section") || "stats")
      .trim()
      .toLowerCase();
    return `/admin/${adminSection || "stats"}`;
  }
  if (
    [
      "home",
      "install",
      "trial",
      "invite",
      "devices",
      "support",
      "settings",
      "login",
    ].includes(screen)
  ) {
    return `/${screen}`;
  }
  return "/home";
};

let initialRoute = routeFromParams();
const mockForRoute = (route) => {
  const normalized = normalizePath(route);
  if (normalized === "/devices") return "devices";
  if (normalized === "/login" || normalized.startsWith("/login/"))
    return "auth";
  return "";
};
const initialMock = params.has("mock")
  ? normalizeRouteMock(params.get("mock"))
  : normalizeRouteMock(mockForRoute(initialRoute) || defaultMock);
const materializedRouteFromRuntime = (route) => {
  const normalized = normalizePath(route);
  if (/^\/admin\/users\/-?\d+$/i.test(normalized)) return "/admin/users";
  if (/^\/admin\/payments\/\d+$/i.test(normalized)) return "/admin/payments";
  if (/^\/admin\/payments\/users\/-?\d+$/i.test(normalized))
    return "/admin/payments";
  if (/^\/admin\/support\/\d+$/i.test(normalized)) return "/admin/support";
  if (/^\/support\/\d+$/i.test(normalized)) return "/support";
  return normalized;
};

const publicPathFromRoute = (route) =>
  `${demoBase}${materializedRouteFromRuntime(route)}`;
const canonicalizeInitialPublicUrl = (route) => {
  const pathname = window.location.pathname.replace(/\/+$/, "") || "/";
  const lowerPathname = pathname.toLowerCase();
  if (
    lowerPathname !== demoBase &&
    !publicRouteAliases.has(pathname.slice(demoBase.length).toLowerCase())
  ) {
    return;
  }
  const normalizedUrl = new URL(window.location.href);
  normalizedUrl.pathname = publicPathFromRoute(route);
  window.history.replaceState(
    null,
    "",
    `${normalizedUrl.pathname}${normalizedUrl.search}${normalizedUrl.hash}`,
  );
};

if (initialMock === "trial" && initialRoute === "/trial") {
  initialRoute = "/home";
  const normalizedUrl = new URL(window.location.href);
  normalizedUrl.pathname = publicPathFromRoute(initialRoute);
  window.history.replaceState(
    null,
    "",
    `${normalizedUrl.pathname}${normalizedUrl.search}${normalizedUrl.hash}`,
  );
} else {
  canonicalizeInitialPublicUrl(initialRoute);
}
params.set("mock", initialMock);
params.delete("path");
params.delete("screen");
params.delete("admin_section");
params.set("path", initialRoute);
frame.src = `${runtimeBase}/app/?${params.toString()}${window.location.hash || ""}`;

const routeFromRuntimeUrl = (url) => {
  if (url.origin !== window.location.origin) return "";
  if (!url.pathname.toLowerCase().startsWith(runtimeBase.toLowerCase()))
    return "";
  const runtimePath = normalizePath(
    url.pathname.slice(runtimeBase.length) || "/home",
  );
  if (runtimePath === "/app" || runtimePath === "/app.html") {
    return normalizePath(url.searchParams.get("path") || "/home");
  }
  return runtimePath;
};
const routeForStateMock = (mock) => {
  if (mock === "devices") return "/devices";
  if (mock === "auth") return "/login";
  return "/home";
};
const runtimeSrc = (route, searchParams = new URLSearchParams()) => {
  const nextParams = new URLSearchParams(searchParams);
  nextParams.delete("screen");
  nextParams.delete("admin_section");
  nextParams.set("path", normalizePath(route));
  return `${runtimeBase}/app/?${nextParams.toString()}${window.location.hash || ""}`;
};
const topbar = document.querySelector(".demo-topbar");
const toggle = document.querySelector(".demo-topbar__toggle");
const hide = document.querySelector(".demo-topbar__hide");
const stateSelect = document.querySelector(".demo-topbar__state-select");

const syncParentUrlFromFrame = () => {
  try {
    const frameUrl = new URL(frame.contentWindow.location.href);
    const route = routeFromRuntimeUrl(frameUrl);
    if (!route) return;

    const nextUrl = new URL(window.location.href);
    nextUrl.pathname = publicPathFromRoute(route);
    nextUrl.searchParams.delete("path");

    const mock = normalizeRouteMock(
      frameUrl.searchParams.get("mock") || params.get("mock"),
    );
    if (mock === defaultMock) nextUrl.searchParams.delete("mock");
    else nextUrl.searchParams.set("mock", mock);
    if (stateSelect) stateSelect.value = normalizeStateMock(mock);

    nextUrl.searchParams.delete("screen");
    nextUrl.searchParams.delete("admin_section");
    const nextPath = `${nextUrl.pathname}${nextUrl.search}${nextUrl.hash}`;
    const currentPath = `${window.location.pathname}${window.location.search}${window.location.hash}`;
    if (nextPath !== currentPath)
      window.history.replaceState(null, "", nextPath);
  } catch (_error) {
    // The iframe is same-origin in docs builds; this keeps local oddities harmless.
  }
};

frame.addEventListener("load", syncParentUrlFromFrame);
window.setInterval(syncParentUrlFromFrame, 750);

const setCollapsed = (collapsed) => {
  topbar?.toggleAttribute("data-collapsed", collapsed);
  toggle?.setAttribute("aria-expanded", String(!collapsed));
};

toggle?.addEventListener("click", () => setCollapsed(false));
hide?.addEventListener("click", () => setCollapsed(true));
if (stateSelect) stateSelect.value = normalizeStateMock(params.get("mock"));
stateSelect?.addEventListener("change", () => {
  const mock = normalizeStateMock(stateSelect.value);
  const nextParams = new URLSearchParams(window.location.search);
  nextParams.delete("path");
  nextParams.delete("screen");
  nextParams.delete("admin_section");
  if (mock === defaultMock) nextParams.delete("mock");
  else nextParams.set("mock", mock);

  const query = nextParams.toString();
  const stateRoute = routeForStateMock(mock);
  const publicUrl = `${demoBase}${stateRoute}${query ? `?${query}` : ""}`;
  window.history.replaceState(null, "", publicUrl);
  frame.src = runtimeSrc(stateRoute, nextParams);
});
