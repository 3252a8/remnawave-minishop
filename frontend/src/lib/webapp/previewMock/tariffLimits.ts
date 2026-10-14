import { DEV_MOCK } from "./devMock.js";
import type { BillingPlan } from "../tariffs.js";

// Synthetic review fixtures: keep the exported snapshot immutable and make the
// same structured limits available to purchase, renewal, gifts and switching.
export function applyTariffLimitsDemo(): void {
  const english = DEV_MOCK.config.language === "en";
  const tariffs: BillingPlan[] = [
    {
      tariff_key: "start",
      tariff_name: "Start",
      description: english
        ? "For everyday use: messaging, websites and music."
        : "Для повседневных задач: мессенджеры, сайты и музыка.",
      billing_model: "period",
      effective_hwid_device_limit: 2,
      monthly_gb: 100,
      traffic_limit_strategy: "MONTH",
      premium_enabled: false,
      premium_monthly_gb: null,
      premium_unlimited: false,
      price: 190,
    },
    {
      tariff_key: "plus",
      tariff_name: "Plus",
      description: english
        ? "For the whole family: video, work and games across several devices. Premium traffic for demanding services."
        : "Для всей семьи: видео, работа и игры на нескольких устройствах. Премиум-трафик для требовательных сервисов.",
      billing_model: "period",
      effective_hwid_device_limit: 5,
      monthly_gb: 300,
      traffic_limit_strategy: "MONTH",
      premium_enabled: true,
      premium_monthly_gb: 50,
      premium_traffic_limit_strategy: "WEEK",
      premium_unlimited: false,
      price: 390,
    },
    {
      tariff_key: "max",
      tariff_name: "Max",
      description: english
        ? "For maximum freedom: unlimited devices and traffic."
        : "Для тех, кому нужен максимум свободы: без ограничений по устройствам и трафику.",
      billing_model: "period",
      effective_hwid_device_limit: 0,
      monthly_gb: 0,
      traffic_limit_strategy: "MONTH",
      premium_enabled: true,
      premium_monthly_gb: null,
      premium_unlimited: true,
      price: 690,
    },
    {
      tariff_key: "flex",
      tariff_name: "Flex",
      description: english
        ? "A flexible option with individual settings. Available limits and terms are confirmed when connecting."
        : "Гибкий вариант для индивидуальных настроек. Доступные лимиты и условия уточняются при подключении.",
      billing_model: "period",
      effective_hwid_device_limit: null,
      monthly_gb: null,
      premium_enabled: true,
      premium_monthly_gb: null,
      premium_unlimited: false,
      price: 290,
    },
    {
      tariff_key: "traffic",
      tariff_name: "Traffic",
      description: english
        ? "A one-time traffic package. Use it at your own pace, without a monthly reset."
        : "Разовая покупка пакета трафика. Используйте его в удобном темпе — без ежемесячного сброса.",
      billing_model: "traffic",
      effective_hwid_device_limit: 1,
      monthly_gb: null,
      traffic_limit_strategy: "NO_RESET",
      premium_enabled: false,
      premium_unlimited: false,
      traffic_packages: [10, 50, 100],
      price: 99,
    },
  ];
  DEV_MOCK.data.settings.traffic_mode = false;
  DEV_MOCK.data.settings.my_devices_enabled = true;
  DEV_MOCK.data.plans = tariffs.flatMap((tariff) => {
    const packages = tariff.billing_model === "traffic" ? [10, 50, 100] : [1, 3, 12];
    return packages.map((units) => ({
      ...tariff,
      id: `${tariff.tariff_key}:${tariff.billing_model}:${units}`,
      title: String(tariff.tariff_name),
      is_default_tariff: tariff.tariff_key === "start",
      sale_mode: tariff.billing_model === "traffic" ? "traffic_package" : "subscription",
      months: units,
      ...(tariff.billing_model === "traffic"
        ? { traffic_gb: units }
        : { duration_days: units === 12 ? 365 : units * 30 }),
      price: Number(tariff.price) * (tariff.billing_model === "traffic" ? units / 10 : units),
      stars_price: Math.ceil((Number(tariff.price) * units) / 2),
      currency: "RUB",
    }));
  });
  DEV_MOCK.data.subscription = {
    ...DEV_MOCK.data.subscription,
    active: true,
    status: "ACTIVE",
    tariff_key: "start",
    tariff_name: "Start",
    tariff_description: String(tariffs[0]?.description || ""),
    billing_model: "period",
    traffic_limit_strategy: "MONTH",
    effective_hwid_device_limit: 2,
    hwid_device_limit: 2,
    traffic_used: "25 GB",
    traffic_limit: "100 GB",
    traffic_limit_bytes: 100 * 1024 ** 3,
    traffic_used_bytes: 25 * 1024 ** 3,
    premium_enabled: false,
    premium_limit_bytes: 0,
    premium_used_bytes: 0,
    premium_is_limited: false,
  };
  const devices = DEV_MOCK.data.devices.devices;
  const visibleDevices = Array.isArray(devices) ? devices.slice(0, 2) : [];
  DEV_MOCK.data.devices = {
    ...DEV_MOCK.data.devices,
    current_devices: visibleDevices.length,
    max_devices: 2,
    max_devices_label: "2",
    devices: visibleDevices,
  };
  DEV_MOCK.data.tariff_change_options = {
    ok: true,
    current: { tariff_key: "start", title: "Start", billing_model: "period", monthly_gb: 100 },
    targets: tariffs.slice(1).map((tariff) => ({
      ...tariff,
      title: tariff.tariff_name,
      actions: [
        {
          mode: tariff.billing_model === "traffic" ? "buy_package" : "buy_period",
          kind: "payment",
          duration_days: tariff.billing_model === "period" ? 30 : undefined,
          months: tariff.billing_model === "traffic" ? 10 : 1,
          traffic_gb: tariff.billing_model === "traffic" ? 10 : undefined,
          price: tariff.price,
          currency: "RUB",
        },
      ],
    })),
  };
}
