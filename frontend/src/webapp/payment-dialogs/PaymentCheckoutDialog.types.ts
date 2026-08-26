import type { CheckoutAddonPreset } from "$lib/webapp/deeplinks.js";
import type { ApiClient } from "$lib/webapp/publicApi.js";
import type {
  CheckoutAddonSelection,
  PaymentMethodView,
  PendingPaymentView,
  PlanView,
  StringAction,
  SubscriptionView,
  TariffView,
  TermUnitLabel,
  Translate,
  VoidAction,
} from "$lib/webapp/types.js";

export type CheckoutPaymentOptions = {
  usePartnerBalance?: boolean;
  checkoutAddons?: CheckoutAddonSelection;
};

type BalancePaymentAction = (options?: CheckoutPaymentOptions) => unknown;
type CheckoutPromoAction = (options?: Pick<CheckoutPaymentOptions, "checkoutAddons">) => unknown;

export type PaymentCheckoutDialogProps = {
  api: ApiClient["api"];
  inline?: boolean;
  createPayment?: BalancePaymentAction;
  hasMultipleTariffs?: boolean;
  methods?: PaymentMethodView[];
  paymentMethodsDisplayMode?: "dropdown" | "buttons" | string;
  pendingPayment?: PendingPaymentView | null;
  payBusy?: boolean;
  paymentModalOpen?: boolean;
  paymentStep?: string;
  plans?: PlanView[];
  selectedMethod?: string;
  selectedPlan?: PlanView | null;
  selectedTariff?: TariffView | null;
  selectedTariffKey?: string;
  selectedTariffPlans?: PlanView[];
  renewHwidDevices?: boolean;
  singleTariffMode?: boolean;
  subscription?: SubscriptionView;
  subscriptionPurchaseDescription?: string;
  tariffCatalog?: TariffView[];
  tariffMode?: boolean;
  trafficMode?: boolean;
  closePaymentModal?: VoidAction;
  checkoutPromoAppliedCode?: string;
  checkoutPromoInput?: string;
  checkoutPromoIsError?: boolean;
  checkoutPromoPriceText?: string;
  checkoutPromoEffectiveAmount?: number;
  checkoutPromoStatus?: string;
  checkoutPromoDiscountPercent?: number;
  checkoutPromoAppliesTo?: string;
  checkoutPromoMinSubscriptionMonths?: number | null;
  checkoutPromoMinTrafficGb?: number | null;
  checkoutAddonPreset?: CheckoutAddonPreset | null;
  applyCheckoutPromo?: CheckoutPromoAction;
  backToTariffList?: VoidAction;
  clearCheckoutPromo?: VoidAction;
  continueWithSelectedTariff?: VoidAction;
  resumePendingPayment?: (payment: PendingPaymentView) => void;
  selectTariff?: (tariff: TariffView) => void;
  setCheckoutPromoInput?: StringAction;
  t?: Translate;
  termUnitLabel?: TermUnitLabel;
};
