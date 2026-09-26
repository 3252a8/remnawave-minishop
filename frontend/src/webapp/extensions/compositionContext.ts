import type { ApiClient } from "$lib/webapp/publicApi";
import type { UserExtensionPlugin } from "$lib/webapp/extensionHost";
import type { Translate } from "$lib/webapp/types";

export const USER_COMPOSITION = Symbol("user-ui-composition-v1");
export interface UserCompositionContext {
  readonly plugins: readonly UserExtensionPlugin[];
  readonly client: ApiClient | undefined;
  readonly t: Translate;
  readonly language: string;
  readonly routePrefix: string;
  readonly context: Record<string, unknown>;
}
