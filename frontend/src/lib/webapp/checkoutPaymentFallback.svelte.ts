import { untrack } from "svelte";

export function createCheckoutPaymentFallback(isOpen: () => boolean, identity: () => string) {
  let failedMethods = $state<string[]>([]);
  let activeContext = $state("");
  let generation = 0;
  const context = $derived(isOpen() ? identity() : "");

  $effect(() => {
    const next = context;
    untrack(() => {
      if (activeContext === next) return;
      generation += 1;
      activeContext = next;
      failedMethods = [];
    });
  });

  return {
    get failedMethods() {
      return failedMethods;
    },
    onUnavailable(): (method: string) => void {
      const attemptContext = context;
      const attemptGeneration = generation;
      return (method) => {
        if (!attemptContext || context !== attemptContext || generation !== attemptGeneration)
          return;
        failedMethods = [...failedMethods.filter((id) => id !== method), method];
      };
    },
  };
}
