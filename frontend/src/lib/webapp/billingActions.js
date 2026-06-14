export function createBillingActions({ api }) {
  async function fetchTopupOptions(kind) {
    return api(`/tariffs/topup-options?kind=${encodeURIComponent(kind)}`);
  }

  async function fetchDeviceTopupOptions() {
    return api("/devices/topup-options");
  }

  async function fetchTariffChangeOptions() {
    return api("/tariffs/change-options");
  }

  async function postPayment(body) {
    return api("/payments", { method: "POST", body: JSON.stringify(body) });
  }

  async function fetchPaymentStatus(paymentId) {
    return api(`/payments/${encodeURIComponent(paymentId)}`);
  }

  async function postTariffChange(body) {
    return api("/tariffs/change", { method: "POST", body: JSON.stringify(body) });
  }

  async function postTariffChangePayment(body) {
    return api("/tariffs/change-payment", { method: "POST", body: JSON.stringify(body) });
  }

  async function postAutoRenew(enabled) {
    return api("/subscription/auto-renew", {
      method: "POST",
      body: JSON.stringify({ enabled: Boolean(enabled) }),
    });
  }

  function planPaymentBody(plan, method, options = {}) {
    return {
      months: plan.months,
      traffic_gb: plan.traffic_gb,
      device_count: plan.device_count,
      tariff_key: plan.tariff_key,
      sale_mode: plan.sale_mode,
      renew_hwid_devices: Boolean(options.renewHwidDevices),
      method,
    };
  }

  function topupPaymentBody(plan, method, fallbackTariffKey) {
    return {
      months: plan.months,
      traffic_gb: plan.traffic_gb,
      tariff_key: plan.tariff_key || fallbackTariffKey,
      sale_mode: plan.sale_mode || "topup",
      method,
    };
  }

  function deviceTopupPaymentBody(plan, method, fallbackTariffKey) {
    return {
      months: plan.device_count || plan.months,
      device_count: plan.device_count || plan.months,
      tariff_key: plan.tariff_key || fallbackTariffKey,
      sale_mode: plan.sale_mode || "hwid_devices",
      method,
    };
  }

  function changePaymentBody(action, target, method) {
    if (action.mode === "buy_package") {
      return {
        tariff_key: target.tariff_key,
        traffic_gb: action.traffic_gb,
        months: action.traffic_gb,
        sale_mode: "topup",
        method,
      };
    }
    if (action.mode === "buy_period") {
      return {
        tariff_key: target.tariff_key,
        months: action.months,
        method,
      };
    }
    return { tariff_key: target.tariff_key, method };
  }

  return {
    fetchTopupOptions,
    fetchDeviceTopupOptions,
    fetchTariffChangeOptions,
    postPayment,
    fetchPaymentStatus,
    postTariffChange,
    postTariffChangePayment,
    postAutoRenew,
    planPaymentBody,
    topupPaymentBody,
    deviceTopupPaymentBody,
    changePaymentBody,
  };
}
