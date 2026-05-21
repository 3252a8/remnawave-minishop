import { mount, unmount } from "svelte";

import AdminPanel from "./admin/AdminPanel.svelte";
import "./styles-admin.css";

function mountAdminPanel(target, props = {}) {
  if (!target) throw new Error("admin_mount_target_missing");

  const currentProps = { ...props };
  const instance = mount(AdminPanel, { target, props: currentProps });
  let destroyed = false;

  return {
    update(nextProps = {}) {
      if (destroyed) return;
      Object.assign(currentProps, nextProps);

      if (typeof instance.$set === "function") {
        instance.$set(nextProps);
        return;
      }

      for (const [key, value] of Object.entries(nextProps)) {
        if (key in instance) instance[key] = value;
      }
    },
    destroy() {
      if (destroyed) return;
      destroyed = true;
      void unmount(instance);
      target.replaceChildren();
    },
  };
}

window.SubscriptionWebAppAdmin = {
  AdminPanel,
  mount: mountAdminPanel,
};
window.SubscriptionWebAppAdminPanel = AdminPanel;
window.dispatchEvent(
  new CustomEvent("subscription-webapp-admin-ready", {
    detail: window.SubscriptionWebAppAdmin,
  })
);
