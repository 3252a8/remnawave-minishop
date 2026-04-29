<script>
  import { Gift, Home, Settings } from "lucide-svelte";

  export let active = "home";
</script>

<nav class="bottom-nav static">
  <button class:active={active === "home"} type="button"><Home size={20} /><span>Главная</span></button>
  <button class:active={active === "invite"} type="button"><Gift size={20} /><span>Пригласить</span></button>
  <button class:active={active === "settings"} type="button"><Settings size={20} /><span>Настройки</span></button>
</nav>
