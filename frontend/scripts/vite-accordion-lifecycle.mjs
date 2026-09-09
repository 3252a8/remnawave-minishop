/**
 * bits-ui 2.19.0 queues Accordion measurements after tick without cancelling
 * them when the owning watch is destroyed. Keep the shared component and
 * cancel that callback before it reads a disposed Svelte derived.
 * This narrow build compatibility patch must be reviewed on a bits-ui update.
 */
export function accordionLifecycleFix() {
  return {
    name: "minishop-accordion-lifecycle",
    enforce: "pre",
    transform(code, id) {
      const filename = id.replaceAll("\\", "/").split("?")[0];
      if (!filename.endsWith("/bits-ui/dist/bits/accordion/accordion.svelte.js")) return;
      const start = code.indexOf("    #updateDimensions = ([_, node]) => {");
      const end = code.indexOf("    get shouldRender()", start);
      if (start < 0 || end < 0)
        throw new Error("Review the bits-ui Accordion lifecycle fix for the installed version.");
      const original = code.slice(start, end);
      if (original.includes("cancelledMeasurement")) return;
      if (!original.includes("        afterTick(() => {") || !original.endsWith("    };\n"))
        throw new Error(
          "Unexpected Accordion measurement implementation; review the lifecycle fix."
        );
      const measurement = original
        .replace(
          "        afterTick(() => {",
          "        let cancelledMeasurement = false;\n" +
            "        afterTick(() => {\n" +
            "            if (cancelledMeasurement) return;"
        )
        .replace(/ {4}};\n$/, "        return () => { cancelledMeasurement = true; };\n    };\n");
      return { code: code.slice(0, start) + measurement + code.slice(end), map: null };
    },
  };
}
