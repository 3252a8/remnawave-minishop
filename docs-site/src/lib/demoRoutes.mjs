export const demoUserRoutes = [
  "home",
  // Checkout renders home with plan selection open; it still needs a page so
  // the static demo serves the route.
  "plans",
  "checkout",
  "install",
  "trial",
  "invite",
  "devices",
  "support",
  "settings",
  "login",
  "login/password",
];

export const demoAdminRoutes = [
  "stats",
  "users",
  "payments",
  "promos",
  "gifts",
  "partners",
  "ads",
  "broadcast",
  "logs",
  "support",
  "tariffs",
  "appearance",
  "translations",
  "backups",
  "plugins",
  "settings",
];

export const demoPublicRouteAliases = ["app"];

export const demoPublicRoutes = [
  ...demoPublicRouteAliases,
  ...demoUserRoutes,
  "emails",
  "admin",
  ...demoAdminRoutes.map((route) => `admin/${route}`),
];

export const demoRuntimeRoutes = [
  ...demoUserRoutes,
  "admin",
  ...demoAdminRoutes.map((route) => `admin/${route}`),
];
