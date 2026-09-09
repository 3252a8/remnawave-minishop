// Existing native fields have explicit, shrinking budgets. New screens get none.
// These controls need their own visual baseline before migrating their styling.
export const nativeFieldBaseline = [
  {
    file: "src/webapp/payment-dialogs/BalanceTopupDialog.svelte",
    control: "input:number",
    count: 1,
    reason: "Animated amount field with overlaid digits",
  },
  {
    file: "src/webapp/checkout/CheckoutEntryScreen.svelte",
    control: "input:email",
    count: 1,
    reason: "Legacy standalone guest checkout layout",
  },
  {
    file: "src/admin/sections/PaymentDetailModal.svelte",
    control: "input:checkbox",
    count: 2,
    reason: "Legacy manual-operation confirmation controls",
  },
  {
    file: "src/admin/sections/PaymentDetailModal.svelte",
    control: "textarea",
    count: 1,
    reason: "Legacy manual-operation reason layout",
  },
  {
    file: "src/admin/sections/user-detail/UserMessageComposerCard.svelte",
    control: "input:checkbox",
    count: 2,
    reason: "Legacy delivery-channel controls",
  },
  {
    file: "src/lib/richtext/RichTextEditor.svelte",
    control: "input:url",
    count: 1,
    reason: "Editor-owned link form",
  },
  {
    file: "src/lib/richtext/RichTextEditor.svelte",
    control: "textarea",
    count: 1,
    reason: "Editor-owned HTML source surface",
  },
];

function literalAttribute(node, name) {
  const attribute = node.startTag.attributes.find(
    (item) => item.type === "SvelteAttribute" && item.key.name === name
  );
  return attribute?.value?.every((item) => item.type === "SvelteLiteral")
    ? attribute.value.map((item) => item.value).join("")
    : "";
}

export default {
  rules: {
    "native-controls": {
      meta: {
        type: "problem",
        schema: [],
        messages: {
          native: "Use the shared UI component for {{control}}. See CONTRIBUTING.md §4.1.",
          budget:
            "Native-field baseline for {{control}} changed ({{actual}}/{{expected}}). Migrate to the shared component and shrink the documented baseline; do not add an exception for new UI.",
          button:
            "Use Button/AdminButton instead of styling a native button with shared button classes.",
          toolbar:
            "Use AdminListToolbar instead of legacy list-toolbar markup. See CONTRIBUTING.md §4.1.",
        },
      },
      create(context) {
        const filename = context.filename.replaceAll("\\", "/");
        const baseline = nativeFieldBaseline.filter((item) => filename.endsWith("/" + item.file));
        const seen = new Map();
        return {
          SvelteElement(node) {
            if (node.kind !== "html") return;
            const tag = node.name.name;
            const classSource = node.startTag.attributes
              .filter(
                (item) =>
                  (item.type === "SvelteAttribute" && item.key.name === "class") ||
                  (item.type === "SvelteDirective" && item.kind === "Class")
              )
              .map((item) => context.sourceCode.getText(item))
              .join(" ");
            if (
              filename.includes("/src/admin/") &&
              /(?:[\s:"'`])(?:admin-toolbar(?:-card|-search)?|partners-filters|partners-search|support-admin-toolbar|support-admin-filter-row|support-admin-search)(?=[\s="'`]|$)/.test(
                classSource
              )
            ) {
              context.report({ node: node.startTag, messageId: "toolbar" });
            }
            if (
              tag === "button" &&
              /(?:[\s:"'`])(?:admin-btn|btn)(?:-[\w-]+)?(?=[\s="'`]|$)/.test(classSource)
            ) {
              context.report({ node: node.startTag, messageId: "button" });
            }
            if (tag !== "input" && tag !== "textarea") return;
            const control =
              tag === "input" ? `input:${literalAttribute(node, "type") || "text"}` : tag;
            if (baseline.some((item) => item.control === control)) {
              seen.set(control, (seen.get(control) || 0) + 1);
            } else context.report({ node: node.startTag, messageId: "native", data: { control } });
          },
          "Program:exit"(node) {
            for (const item of baseline) {
              const actual = seen.get(item.control) || 0;
              if (actual !== item.count)
                context.report({
                  node,
                  messageId: "budget",
                  data: { control: item.control, actual, expected: item.count },
                });
            }
          },
        };
      },
    },
  },
};
