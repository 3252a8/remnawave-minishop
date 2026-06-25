import { withRoutePrefix } from "./routes.js";

type PasswordRouteWindow = {
  history: {
    pushState: (data: unknown, unused: string, url?: string | URL | null) => void;
    replaceState: (data: unknown, unused: string, url?: string | URL | null) => void;
  };
  location: {
    hash: string;
    pathname: string;
    protocol: string;
    search: string;
  };
};

export type SyncPasswordLoginPathOptions = {
  cleanDocsDemoRouteQuery?: () => void;
  enabled: boolean;
  getWindow?: () => PasswordRouteWindow;
  isDocsDemo?: boolean;
  replace?: boolean;
  routePrefix?: string;
};

export function isPasswordLoginPath(pathname: unknown) {
  return (
    String(pathname || "")
      .replace(/\/+$/, "")
      .toLowerCase() === "/login/password"
  );
}

export function syncPasswordLoginPath({
  cleanDocsDemoRouteQuery = () => {},
  enabled,
  getWindow = () => window,
  isDocsDemo = false,
  replace = false,
  routePrefix = "",
}: SyncPasswordLoginPathOptions) {
  const currentWindow = getWindow();
  if (currentWindow.location.protocol === "file:") return false;
  const targetPath = enabled ? "/login/password" : isDocsDemo ? "/login" : "/";
  const targetRuntimePath = isDocsDemo ? withRoutePrefix(targetPath, routePrefix) : targetPath;
  if (currentWindow.location.pathname === targetRuntimePath) return false;
  const nextUrl = `${targetRuntimePath}${currentWindow.location.search}${currentWindow.location.hash}`;
  currentWindow.history[replace ? "replaceState" : "pushState"](null, "", nextUrl);
  if (isDocsDemo) cleanDocsDemoRouteQuery();
  return true;
}
