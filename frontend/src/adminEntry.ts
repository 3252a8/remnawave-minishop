import { mount, unmount, type ComponentProps } from "svelte";

import AdminPanel from "./admin/AdminPanel.svelte";
import { createAdminMountProps, type AdminMountProps } from "./adminMountProps.svelte.js";
import "./styles-admin.css";

function mountAdminPanel(target: HTMLElement, props: AdminMountProps = {}) {
  if (!target) throw new Error("admin_mount_target_missing");

  const mountProps = createAdminMountProps(props);
  const instance = mount(AdminPanel, {
    target,
    props: mountProps.props as ComponentProps<typeof AdminPanel>,
  });
  let destroyed = false;

  return {
    update(nextProps: AdminMountProps = {}) {
      if (destroyed) return;
      mountProps.update(nextProps);
    },
    destroy() {
      if (destroyed) return;
      destroyed = true;
      void unmount(instance);
      target.replaceChildren();
    },
  };
}

const adminGlobal = window as unknown as Record<string, unknown>;
adminGlobal.SubscriptionWebAppAdmin = {
  AdminPanel,
  mount: mountAdminPanel,
};
adminGlobal.SubscriptionWebAppAdminPanel = AdminPanel;
window.dispatchEvent(
  new CustomEvent("subscription-webapp-admin-ready", {
    detail: adminGlobal.SubscriptionWebAppAdmin,
  })
);
