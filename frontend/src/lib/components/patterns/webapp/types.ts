/** Shared shapes for the customer-facing pattern components. */

/**
 * One resolved button attached to a support message.
 *
 * Loose on purpose: the same component renders messages coming from the admin
 * store and from the customer store, whose generated types differ in nothing
 * that matters here.
 */
export type TicketMessageButtonLike = {
  label?: string;
  url?: string;
  kind?: string;
  promo_code?: string;
  section?: string;
  icon_custom_emoji_id?: string | null;
  icon_emoji?: string;
};
