import { openUrlWithHiddenAnchor, readExternalAppLaunchTarget } from "./appLinks.js";

type AppLaunchActionDeps = {
  openTarget?: (url: string) => void;
  readTarget?: () => string;
  setAppLaunchTarget: (target: string) => void;
};

export function createAppLaunchActions({
  openTarget = openUrlWithHiddenAnchor,
  readTarget = readExternalAppLaunchTarget,
  setAppLaunchTarget,
}: AppLaunchActionDeps) {
  function refreshAppLaunchTarget() {
    const target = readTarget();
    setAppLaunchTarget(target);
    return target;
  }

  function openAppLaunchTarget(nextTarget = "") {
    const target = String(nextTarget || refreshAppLaunchTarget() || "").trim();
    if (!target) return false;
    setAppLaunchTarget(target);
    openTarget(target);
    return true;
  }

  return {
    openAppLaunchTarget,
    refreshAppLaunchTarget,
  };
}
