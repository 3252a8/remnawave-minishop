<script lang="ts">
  import {
    CircleQuestionMark,
    ExternalLink,
    Gift,
    Globe2,
    Home,
    Info,
    LifeBuoy,
    MessageSquare,
    Send,
    Shield,
    Star,
    Users,
    Zap,
  } from "$components/ui/icons.js";

  let { icon = "" }: { icon?: string } = $props();
</script>

{#if icon === "CircleQuestionMark"}<CircleQuestionMark size={21} />
{:else if icon === "ExternalLink"}<ExternalLink size={21} />
{:else if icon === "Gift"}<Gift size={21} />
{:else if icon === "Globe2"}<Globe2 size={21} />
{:else if icon === "Home"}<Home size={21} />
{:else if icon === "Info"}<Info size={21} />
{:else if icon === "LifeBuoy"}<LifeBuoy size={21} />
{:else if icon === "MessageSquare"}<MessageSquare size={21} />
{:else if icon === "Send"}<Send size={21} />
{:else if icon === "Shield"}<Shield size={21} />
{:else if icon === "Star"}<Star size={21} />
{:else if icon === "Users"}<Users size={21} />
{:else if icon === "Zap"}<Zap size={21} />
{:else if icon}<span class="menu-button-emoji" aria-hidden="true">{icon}</span>{/if}

<style>
  .menu-button-emoji {
    display: inline-grid;
    min-width: 21px;
    place-items: center;
    font-size: 19px;
    line-height: 1;
  }
</style>
