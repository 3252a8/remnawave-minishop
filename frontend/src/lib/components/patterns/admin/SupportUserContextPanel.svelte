<script>
  import { AdminBadge, AdminButton } from "$components/patterns/admin/index.js";
  import { User } from "$components/ui/icons.js";

  let { ticket, snapshot = {}, at = (key) => key, onOpenUser = () => {} } = $props();

  const user = $derived(ticket?.user || {});
  const displayName = $derived(
    snapshot?.name || user.username || user.email || user.user_id || "-"
  );
  const avatarUrl = $derived(user?.avatar_url || user?.photo_url || "");
  const avatarInitials = $derived(computeInitials(user, displayName));
  const canOpenUser = $derived(
    user.user_id !== undefined && user.user_id !== null && user.user_id !== ""
  );
  const identityMeta = $derived(
    [user.email, canOpenUser ? `ID ${user.user_id}` : ""].filter(Boolean).join(" / ") || "-"
  );
  const contextItems = $derived([
    { label: at("support_tariff", {}, "Тариф"), value: snapshot?.tariff || "-" },
    { label: at("support_status", {}, "Статус"), value: snapshot?.panel_status || "-" },
    { label: at("support_remaining", {}, "Осталось"), value: snapshot?.remaining || "-" },
  ]);

  function computeInitials(u, fallback) {
    const source =
      [u?.first_name, u?.last_name].filter(Boolean).join(" ").trim() ||
      u?.username ||
      u?.email ||
      String(fallback || "");
    const clean = String(source).replace(/^@/, "").trim();
    const parts = clean.split(/\s+/).filter(Boolean);
    if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
    return (clean.slice(0, 2) || "U").toUpperCase();
  }
</script>

<section class="support-user-context" aria-label={at("support_user_context", {}, "User")}>
  <div class="support-user-context-head">
    <span class="support-user-context-avatar" aria-hidden="true">
      {#if avatarUrl}
        <img src={avatarUrl} alt="" loading="lazy" referrerpolicy="no-referrer" />
      {:else}
        {avatarInitials}
      {/if}
    </span>
    <div class="support-user-context-identity">
      <strong>{displayName}</strong>
      <small>{identityMeta}</small>
      {#if user.is_banned}
        <AdminBadge variant="danger">{at("status_banned", {}, "Бан")}</AdminBadge>
      {/if}
    </div>
  </div>

  <div class="support-user-context-metrics">
    {#each contextItems as item (item.label)}
      <span>
        <small>{item.label}</small>
        <strong>{item.value}</strong>
      </span>
    {/each}
  </div>

  <div class="support-user-context-actions">
    <AdminButton
      class="support-user-card-btn"
      data-admin-action="open-support-user-card"
      variant="ghost"
      size="icon"
      disabled={!canOpenUser}
      onclick={() => onOpenUser(user.user_id)}
      aria-label={at("support_open_user", {}, "Карточка")}
      title={at("support_open_user", {}, "Карточка")}
    >
      <User size={14} />
    </AdminButton>
  </div>
</section>
