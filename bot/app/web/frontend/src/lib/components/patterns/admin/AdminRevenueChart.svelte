<script>
  import { onMount, tick } from "svelte";
  import uPlot from "uplot";
  import "uplot/dist/uPlot.min.css";

  /** `{ date: ISO date string, amount: number }[]` */
  export let series = [];
  /** Total plot height in CSS px (axes + canvas). */
  export let plotHeight = 204;
  export let fmtMoney = (v, _currency) => String(v);
  /** @type {string} */
  export let currency = "RUB";
  /** uPlot live legend: column header for the time (x) series */
  export let legendTimeLabel = "Time";
  /** uPlot live legend: column header for the value (y) series */
  export let legendValueLabel = "Value";

  let hostEl;
  let plot;
  let resizeObserver;
  let syncTimer = 0;
  /** Rebuild plot when legend copy changes (language), since series labels are init-only */
  let builtLegendSig = "";

  function readCssColor(name, fallback) {
    if (typeof document === "undefined") return fallback;
    const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return raw || fallback;
  }

  function parseDayUnix(iso) {
    const s = String(iso || "");
    const t = Date.parse(s.includes("T") ? s : `${s}T12:00:00Z`);
    if (!Number.isFinite(t)) return 0;
    return Math.floor(t / 1000);
  }

  function toAlignedData(rows) {
    if (!rows?.length) return null;
    const xs = rows.map((p) => parseDayUnix(p.date));
    const ys = rows.map((p) => Number(p.amount) || 0);
    return [xs, ys];
  }

  function yAxisTickLabels(values) {
    return values.map((v) => fmtMoney(Number(v), currency));
  }

  /** uPlot passes already-formatted tick strings; reserve enough gutter so amounts are not clipped */
  function yAxisGutterWidth(_u, values) {
    const pad = 14;
    const charPx = 6.1;
    const maxChars = (values || []).reduce((m, v) => Math.max(m, String(v ?? "").length), 0);
    return Math.min(104, Math.max(58, Math.ceil(pad + maxChars * charPx)));
  }

  /** Axis `size`: height (x / bottom) or width (y / left) in CSS px — only customize the y gutter */
  function axisBandSize(_u, values, axisIdx) {
    if (axisIdx !== 1) return 32;
    return yAxisGutterWidth(_u, values);
  }

  function buildOpts(width) {
    const w = Math.max(80, Math.floor(width));
    const muted = readCssColor("--admin-muted", "#9aa7a2");
    const border = readCssColor("--admin-border", "rgba(255,255,255,0.12)");
    const accent = readCssColor("--accent", "#00fe7a");
    const lineStroke = readCssColor("--admin-text", "#e8f0ec");

    return {
      width: w,
      height: plotHeight,
      class: "admin-uplot",
      pxAlign: true,
      padding: [10, 12, 12, 10],
      legend: {
        show: true,
        live: true,
        markers: { show: true, width: 10, stroke: accent, fill: accent },
      },
      cursor: {
        drag: { x: false, y: false },
        points: { size: 7, width: 1, stroke: accent },
      },
      scales: {
        x: { time: true },
        y: { range: [0, null] },
      },
      series: [
        { label: legendTimeLabel },
        {
          label: legendValueLabel,
          paths: uPlot.paths.spline(),
          stroke: lineStroke,
          width: 2,
          cap: "round",
          fill: "rgba(120, 140, 132, 0.14)",
        },
      ],
      axes: [
        {
          stroke: muted,
          gap: 8,
          grid: { show: true, stroke: border, width: 1 },
          ticks: { stroke: border },
          font: "11px system-ui,Segoe UI,sans-serif",
        },
        {
          stroke: muted,
          size: axisBandSize,
          gap: 8,
          grid: { show: true, stroke: border, width: 1 },
          ticks: { stroke: border },
          font: "10px system-ui,Segoe UI,sans-serif",
          values: (u, ticks) => yAxisTickLabels(ticks),
        },
      ],
    };
  }

  function syncChart() {
    if (!hostEl) return;
    const d = toAlignedData(series);
    const legendSig = `${legendTimeLabel}\0${legendValueLabel}`;
    if (!d) {
      plot?.destroy();
      plot = undefined;
      builtLegendSig = "";
      return;
    }
    const w = Math.max(80, Math.floor(hostEl.clientWidth));
    if (plot && builtLegendSig !== legendSig) {
      plot.destroy();
      plot = undefined;
    }
    if (!plot) {
      plot = new uPlot(buildOpts(w), d, hostEl);
      builtLegendSig = legendSig;
      return;
    }
    plot.setData(d, true);
    plot.setSize({ width: w, height: plotHeight });
  }

  function scheduleSync() {
    if (typeof window === "undefined") return;
    clearTimeout(syncTimer);
    syncTimer = window.setTimeout(() => {
      syncTimer = 0;
      syncChart();
    }, 0);
  }

  let rafId = 0;

  onMount(() => {
    rafId = requestAnimationFrame(() => {
      void tick().then(() => {
        scheduleSync();
        if (!hostEl || typeof ResizeObserver === "undefined") return;
        resizeObserver = new ResizeObserver(() => scheduleSync());
        resizeObserver.observe(hostEl);
      });
    });
    return () => {
      cancelAnimationFrame(rafId);
      clearTimeout(syncTimer);
      resizeObserver?.disconnect();
      resizeObserver = undefined;
      plot?.destroy();
      plot = undefined;
      builtLegendSig = "";
    };
  });

  $: if (hostEl) {
    series;
    plotHeight;
    legendTimeLabel;
    legendValueLabel;
    scheduleSync();
  }
</script>

<div class="admin-revenue-uplot-host" bind:this={hostEl}></div>
