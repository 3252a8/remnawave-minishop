<script lang="ts">
  type Provider = "google" | "telegram" | "yandex";

  let { provider, size = 18 }: { provider: Provider; size?: number } = $props();
</script>

{#if provider === "google"}
  <svg
    class="auth-provider-logo"
    data-provider-logo="google"
    width={size}
    height={size}
    viewBox="0 0 48 48"
    aria-hidden="true"
  >
    <path
      fill="#ffc107"
      d="M43.6 20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34.1 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.7-.4-4"
    />
    <path
      fill="#ff3d00"
      d="m6.3 14.7 6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34.1 6.1 29.3 4 24 4c-7.7 0-14.3 4.3-17.7 10.7"
    />
    <path
      fill="#4caf50"
      d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.1-5.2C29.3 35.1 26.8 36 24 36c-5.2 0-9.7-3.3-11.3-7.9l-6.5 5C9.5 39.6 16.2 44 24 44"
    />
    <path
      fill="#1976d2"
      d="M43.6 20H42 24v8h11.3c-.8 2.3-2.3 4.2-4.4 5.5l6.1 5.2C36.6 39.1 44 33.7 44 24c0-1.3-.1-2.7-.4-4Z"
    />
  </svg>
{:else if provider === "telegram"}
  <svg
    class="auth-provider-logo"
    data-provider-logo="telegram"
    width={size}
    height={size}
    viewBox="0 0 48 48"
    aria-hidden="true"
  >
    <circle cx="24" cy="24" r="20" fill="#2aabee" />
    <path
      fill="#fff"
      d="m34.7 14.4-3.2 18.5c-.2 1.3-1.1 1.6-2.2 1l-5-3.7-2.4 2.3c-.3.3-.5.5-1 .5l.4-5.1 9.3-8.4c.4-.4-.1-.6-.6-.2l-11.5 7.2-5-1.6c-1.1-.3-1.1-1.1.2-1.6l19.5-7.5c.9-.3 1.7.2 1.5 1.6Z"
    />
  </svg>
{:else}
  <svg
    class="auth-provider-logo"
    data-provider-logo="yandex"
    width={size}
    height={size}
    viewBox="0 0 48 48"
    aria-hidden="true"
  >
    <circle cx="24" cy="24" r="20" fill="#fc3f1d" />
    <path
      fill="#fff"
      d="M27.3 35h4.4V13h-6.6c-6.1 0-9.3 3.1-9.3 7.8 0 3.7 1.8 6.1 5.5 8.7L15.2 35h5.2l6.8-6.2-2.4-1.6c-2.9-2-4.3-3.5-4.3-6.7 0-2.8 1.9-4.4 4.8-4.4h2V35Z"
    />
  </svg>
{/if}
