export type AdminMountProps = Record<string, unknown>;

export function createAdminMountProps(initialProps: AdminMountProps = {}) {
  const props = $state({ ...initialProps });

  return {
    props,
    update(nextProps: AdminMountProps = {}) {
      Object.assign(props, nextProps);
    },
  };
}
