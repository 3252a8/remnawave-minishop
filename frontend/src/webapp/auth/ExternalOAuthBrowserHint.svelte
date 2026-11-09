<script lang="ts">
  import Button from "$components/ui/button.svelte";
  import { StatusMessage } from "$components/patterns/webapp/index.js";
  import { openOAuthCabinetInBrowser } from "$lib/webapp/externalOAuthBrowser.js";
  import type { Translate } from "$lib/webapp/types.js";

  let {
    t,
    security = false,
    pluginCabinetPath = "",
  }: { t: Translate; security?: boolean; pluginCabinetPath?: string } = $props();
</script>

<div class="external-oauth-browser-hint" data-external-oauth-browser-hint>
  <StatusMessage>
    {t(pluginCabinetPath ? "wa_plugin_login_browser_hint" : "wa_external_oauth_browser_hint")}
  </StatusMessage>
  <Button
    variant="secondary"
    class="wide"
    onclick={() =>
      openOAuthCabinetInBrowser(security ? "/settings/security" : pluginCabinetPath || "/")}
  >
    {t("wa_external_oauth_open_browser")}
  </Button>
</div>
