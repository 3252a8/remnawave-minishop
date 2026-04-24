import re

html_path = "bot/app/web/templates/subscription_webapp.html"

with open(html_path, 'r', encoding='utf-8') as f:
    html = f.read()

replacements = {
    r'class="flex items-start justify-between gap-3"': 'class="panel-head"',
    r'class="text-lg font-extrabold leading-tight text-\[var\(--text-primary\)\]"': 'class="section-title"',
    r'class="mt-\[3px\] text-\[13px\] text-\[var\(--text-secondary\)\]"': 'class="section-caption"',
    r'class="min-w-0 font-\[family-name:var\(--font-mono\)\] text-\[11px\] font-bold text-\[var\(--text-muted\)\]"': 'class="metric-label"',
    r'class="min-w-0 text-right text-sm font-bold text-\[var\(--text-primary\)\]"': 'class="metric-value"',
    r'class="m-0 text-\[32px\] font-extrabold leading-\[1\.08\] text-\[var\(--text-primary\)\]"': 'class="main-value"',
    r'class="mt-1\.5 mb-0 text-sm leading-\[1\.45\] text-\[var\(--text-secondary\)\]"': 'class="main-caption"',
    r'class="login-text login-status hidden m-0 min-h-5 text-sm leading-\[1\.45\] text-\[var\(--text-secondary\)\]"': 'class="status-text hidden"',
    r'class="login-text login-status hidden"': 'class="status-text hidden"',
    r'class="actions grid min-w-0 grid-cols-\[minmax\(0,1fr\)_48px\] gap-2"': 'class="actions-row"',
    r'class="hidden flex flex-wrap justify-center gap-x-4 gap-y-1\.5"': 'class="legal-links hidden"',
    r'class="flex min-h-12 items-center justify-between gap-3"': 'class="app-header"',
    r'class="flex min-w-0 items-center gap-2\.5"': 'class="app-header-title"',
    r'class="flex min-w-0 items-center gap-2"': 'class="app-header-actions"',
    r'class="flex min-w-0 items-center justify-between gap-2\.5"': 'class="panel-head-sm"',
    r'class="flex min-w-0 items-center justify-center gap-3\.5"': 'class="login-head"',
}

for pattern, repl in replacements.items():
    html = re.sub(pattern, repl, html)

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html)

js_path = "bot/app/web/templates/subscription_webapp.js"
with open(js_path, 'r', encoding='utf-8') as f:
    js = f.read()

js_replacements = {
    r"panelHead: 'flex items-start justify-between gap-3',": "panelHead: 'panel-head',",
    r"flowCaption: 'mt-\[3px\] text-\[13px\] text-\[var\(--text-secondary\)\]',": "flowCaption: 'section-caption',",
    r"sectionTitle: 'text-lg font-extrabold leading-tight text-\[var\(--text-primary\)\]',": "sectionTitle: 'section-title',",
    r"metricLabel: 'min-w-0 font-\[family-name:var\(--font-mono\)\] text-\[11px\] font-bold text-\[var\(--text-muted\)\]',": "metricLabel: 'metric-label',",
    r"metricValue: 'min-w-0 text-right text-sm font-bold text-\[var\(--text-primary\)\]',": "metricValue: 'metric-value',",
    r"referralLinkRow: 'grid min-h-\[58px\] grid-cols-\[minmax\(0,1fr\)_48px\] items-center gap-2\.5 rounded-\[var\(--radius-md\)\] border border-\[var\(--border\)\] bg-\[rgba\(255,255,255,0\.02\)\] px-3 py-\[11px\]',": "referralLinkRow: 'referral-link-row',",
    r"referralLinkValue: 'mt-1 font-\[family-name:var\(--font-mono\)\] text-xs font-bold leading-\[1\.35\] text-\[var\(--text-primary\)\]',": "referralLinkValue: 'referral-link-value',",
    r"bonusRow: 'grid min-h-\[58px\] grid-cols-\[minmax\(0,0\.8fr\)_minmax\(0,1\.2fr\)\] items-center gap-2\.5 rounded-\[var\(--radius-md\)\] border border-\[var\(--border\)\] bg-\[rgba\(255,255,255,0\.02\)\] px-3 py-\[11px\]',": "bonusRow: 'bonus-row',",
    r"empty: 'rounded-\[var\(--radius-md\)\] border border-\[var\(--border\)\] bg-\[rgba\(255,255,255,0\.02\)\] p-\[13px\] text-sm leading-\[1\.45\] text-\[var\(--text-secondary\)\]',": "empty: 'empty-state',",
    r"planCard: 'flex min-h-16 w-full min-w-0 items-center justify-between gap-3 rounded-\[var\(--radius-md\)\] border border-\[var\(--border\)\] bg-\[rgba\(255,255,255,0\.02\)\] p-\[13px\] text-left text-\[var\(--text-primary\)\] transition-\[transform,border-color,background,box-shadow\] hover:-translate-y-0\.5 hover:border-\[color-mix\(in_srgb,var\(--accent\)_42%,var\(--border\)\)\] hover:bg-\[var\(--bg-card-hover\)\]',": "planCard: 'plan-card',",
    r"planCardActive: 'border-\[var\(--accent\)\] bg-\[color-mix\(in_srgb,var\(--accent\)_8%,transparent\)\] ring-1 ring-\[color-mix\(in_srgb,var\(--accent\)_58%,transparent\)\] shadow-\[0_12px_30px_rgba\(0,0,0,0\.2\)\]',": "planCardActive: 'plan-card-active',",
    r"planName: 'block text-\[15px\] font-extrabold leading-tight',": "planName: 'plan-name',",
    r"planMeta: 'mt-1 block font-\[family-name:var\(--font-mono\)\] text-\[11px\] font-bold leading-\[1\.3\] text-\[var\(--text-muted\)\]',": "planMeta: 'plan-meta',",
    r"planPrice: 'block max-w-\[48%\] flex-none text-right font-\[family-name:var\(--font-mono\)\] text-\[15px\] font-extrabold leading-tight text-\[var\(--accent\)\]',": "planPrice: 'plan-price',",
    r"notice: 'rounded-\[var\(--radius-md\)\] border border-\[var\(--border\)\] bg-\[rgba\(255,255,255,0\.02\)\] p-\[13px\] text-sm leading-\[1\.45\] text-\[var\(--text-secondary\)\]',": "notice: 'notice',",
    r"stepNum: 'block font-\[family-name:var\(--font-mono\)\] text-\[11px\] font-extrabold leading-\[1\.1\] text-current',": "stepNum: 'step-num',",
    r"stepName: 'mt-1 block text-xs font-extrabold leading-\[1\.15\] text-current'": "stepName: 'step-name'"
}

for pattern, repl in js_replacements.items():
    js = re.sub(pattern, repl, js)

with open(js_path, 'w', encoding='utf-8') as f:
    f.write(js)

# CSS additions
css_path = "bot/app/web/templates/subscription_webapp.tailwind.css"
with open(css_path, 'r', encoding='utf-8') as f:
    css = f.read()

new_components = """
  .panel-head {
    @apply flex items-start justify-between gap-3;
  }
  .section-title {
    @apply text-lg font-extrabold leading-tight text-[var(--text-primary)];
  }
  .section-caption {
    @apply mt-[3px] text-[13px] text-[var(--text-secondary)];
  }
  .metric-label {
    @apply min-w-0 font-[family-name:var(--font-mono)] text-[11px] font-bold text-[var(--text-muted)];
  }
  .metric-value {
    @apply min-w-0 text-right text-sm font-bold text-[var(--text-primary)];
  }
  .referral-link-row {
    @apply grid min-h-[58px] grid-cols-[minmax(0,1fr)_48px] items-center gap-2.5 rounded-[var(--radius-md)] border border-[var(--border)] bg-[rgba(255,255,255,0.02)] px-3 py-[11px];
  }
  .referral-link-value {
    @apply mt-1 font-[family-name:var(--font-mono)] text-xs font-bold leading-[1.35] text-[var(--text-primary)];
  }
  .bonus-row {
    @apply grid min-h-[58px] grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)] items-center gap-2.5 rounded-[var(--radius-md)] border border-[var(--border)] bg-[rgba(255,255,255,0.02)] px-3 py-[11px];
  }
  .empty-state {
    @apply rounded-[var(--radius-md)] border border-[var(--border)] bg-[rgba(255,255,255,0.02)] p-[13px] text-sm leading-[1.45] text-[var(--text-secondary)];
  }
  .plan-card {
    @apply flex min-h-16 w-full min-w-0 items-center justify-between gap-3 rounded-[var(--radius-md)] border border-[var(--border)] bg-[rgba(255,255,255,0.02)] p-[13px] text-left text-[var(--text-primary)] transition-[transform,border-color,background,box-shadow] hover:-translate-y-0.5 hover:border-[color-mix(in_srgb,var(--accent)_42%,var(--border))] hover:bg-[var(--bg-card-hover)];
    transition-duration: 200ms;
  }
  .plan-card-active {
    @apply border-[var(--accent)] bg-[color-mix(in_srgb,var(--accent)_8%,transparent)] ring-1 ring-[color-mix(in_srgb,var(--accent)_58%,transparent)] shadow-[0_12px_30px_rgba(0,0,0,0.2)];
  }
  .plan-name {
    @apply block text-[15px] font-extrabold leading-tight;
  }
  .plan-meta {
    @apply mt-1 block font-[family-name:var(--font-mono)] text-[11px] font-bold leading-[1.3] text-[var(--text-muted)];
  }
  .plan-price {
    @apply block max-w-[48%] flex-none text-right font-[family-name:var(--font-mono)] text-[15px] font-extrabold leading-tight text-[var(--accent)];
  }
  .notice {
    @apply rounded-[var(--radius-md)] border border-[var(--border)] bg-[rgba(255,255,255,0.02)] p-[13px] text-sm leading-[1.45] text-[var(--text-secondary)];
  }
  .step-num {
    @apply block font-[family-name:var(--font-mono)] text-[11px] font-extrabold leading-[1.1] text-current;
  }
  .step-name {
    @apply mt-1 block text-xs font-extrabold leading-[1.15] text-current;
  }
  .main-value {
    @apply m-0 text-[32px] font-extrabold leading-[1.08] text-[var(--text-primary)];
  }
  .main-caption {
    @apply mt-1.5 mb-0 text-sm leading-[1.45] text-[var(--text-secondary)];
  }
  .status-text {
    @apply m-0 min-h-5 text-sm leading-[1.45] text-[var(--text-secondary)];
  }
  .legal-links {
    @apply flex flex-wrap justify-center gap-x-4 gap-y-1.5;
  }
  .actions-row {
    @apply grid min-w-0 grid-cols-[minmax(0,1fr)_48px] gap-2;
  }
  .app-header {
    @apply flex min-h-12 items-center justify-between gap-3;
  }
  .app-header-title {
    @apply flex min-w-0 items-center gap-2.5;
  }
  .app-header-actions {
    @apply flex min-w-0 items-center gap-2;
  }
  .panel-head-sm {
    @apply flex min-w-0 items-center justify-between gap-2.5;
  }
  .login-head {
    @apply flex min-w-0 items-center justify-center gap-3.5;
  }
"""

css_split = css.split('.btn {')
new_css = css_split[0] + new_components + '\n  .btn {' + css_split[1]

with open(css_path, 'w', encoding='utf-8') as f:
    f.write(new_css)

print("Done")
