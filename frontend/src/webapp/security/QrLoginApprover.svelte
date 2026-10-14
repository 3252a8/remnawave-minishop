<script lang="ts">
  /**
   * Approves a sign-in on another device from this signed-in session. Telegram's
   * own scanner is used inside its phone apps; anywhere else the page scans with
   * the camera. A sign-in link that a phone camera opened in this browser is
   * picked up as well, so it lands on the same confirmation.
   */
  import { onMount } from "svelte";
  import type { ApiClient } from "$lib/webapp/publicApi.js";
  import {
    parseQrLoginCode,
    takeQrLoginCodeFromLocation,
    telegramQrScanner,
  } from "$lib/webapp/qrLogin.js";
  import type { Translate } from "$lib/webapp/types.js";
  import QrLoginApproveDialog from "./QrLoginApproveDialog.svelte";
  import QrScanDialog from "./QrScanDialog.svelte";

  type Props = {
    api: ApiClient["api"];
    t: Translate;
    /** The shop's host, shown so people know what to open on the other device. */
    site?: string;
  };

  let { api, t, site = "" }: Props = $props();

  const scanHint = $derived(site ? t("wa_qr_scan_hint_site", { site }) : t("wa_qr_scan_hint"));

  let scanOpen = $state(false);
  let approveOpen = $state(false);
  let approveCode = $state("");

  function approve(code: string): void {
    approveCode = code;
    approveOpen = true;
  }

  export function scan(): void {
    const scanner = telegramQrScanner(
      typeof window === "undefined" ? null : window.Telegram?.WebApp
    );
    if (!scanner) {
      scanOpen = true;
      return;
    }
    scanner.showScanQrPopup({ text: scanHint }, (text: string) => {
      const code = parseQrLoginCode(text);
      if (!code) return false;
      approve(code);
      return true;
    });
  }

  onMount(() => {
    const code = takeQrLoginCodeFromLocation();
    if (code) approve(code);
  });
</script>

<QrScanDialog
  open={scanOpen}
  {t}
  hint={scanHint}
  onscan={(code) => {
    scanOpen = false;
    approve(code);
  }}
  onclose={() => (scanOpen = false)}
/>
<QrLoginApproveDialog
  open={approveOpen}
  code={approveCode}
  {api}
  {t}
  onclose={() => (approveOpen = false)}
/>
