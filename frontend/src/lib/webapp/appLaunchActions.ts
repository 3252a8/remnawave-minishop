import { openUrlWithHiddenAnchor, readExternalAppLaunchTarget } from "./appLinks.js";
import { shellState } from "./shellState.svelte";

type AppLaunchActionDeps = {
  openTarget?: (url: string) => void;
  readTarget?: () => string;
};

export function createAppLaunchActions({
  openTarget = openUrlWithHiddenAnchor,
  readTarget = readExternalAppLaunchTarget,
}: AppLaunchActionDeps) {
  function refreshAppLaunchTarget() {
    const target = readTarget();
    shellState.appLaunchTarget = target;
    return target;
  }

  function openAppLaunchTarget(nextTarget = "") {
    const target = String(nextTarget || refreshAppLaunchTarget() || "").trim();
    if (!target) return false;
    shellState.appLaunchTarget = target;
    openTarget(target);
    return true;
  }

  return {
    openAppLaunchTarget,
    refreshAppLaunchTarget,
  };
}
