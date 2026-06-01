export const demoUserRoutes = [
  "home",
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
  "ads",
  "broadcast",
  "logs",
  "support",
  "tariffs",
  "appearance",
  "translations",
  "backups",
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
