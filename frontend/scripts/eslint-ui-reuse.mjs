// Existing native fields have explicit, shrinking budgets. New screens get none.
// These specialized surfaces own behavior beyond a standard form field.
export const nativeFieldBaseline = [
  {
    file: "src/webapp/payment-dialogs/BalanceTopupDialog.svelte",
    control: "input:text",
    count: 1,
    reason: "Animated amount field with overlaid digits",
  },
  {
    file: "src/lib/richtext/RichTextEditor.svelte",
    control: "textarea",
    count: 1,
    reason: "Editor-owned HTML source surface",
  },
];

const specializedInputTypes = new Map([
  ...["date", "datetime-local", "time", "month", "week"].map((type) => [type, "DateInput"]),
  ["checkbox", "Checkbox"],
  ["radio", "RadioGroupItem"],
  ["range", "RangeInput/Slider"],
  ["color", "ColorInput"],
  ["file", "FileInput"],
  ...["button", "submit", "reset"].map((type) => [type, "Button/AdminButton"]),
]);

function expressionStrings(expression) {
  if (expression?.type === "Literal" && typeof expression.value === "string")
    return [expression.value];
  if (expression?.type === "TemplateLiteral" && expression.expressions.length === 0)
    return [expression.quasis[0].value.cooked];
  if (expression?.type === "ConditionalExpression")
    return [
      ...expressionStrings(expression.consequent),
      ...expressionStrings(expression.alternate),
    ];
  if (expression?.type === "LogicalExpression")
    return [...expressionStrings(expression.left), ...expressionStrings(expression.right)];
  return [];
}

function attributeStrings(node, name) {
  const attribute = node.startTag.attributes.find(
    (item) => item.type === "SvelteAttribute" && item.key.name === name
  );
  if (attribute?.value?.every((item) => item.type === "SvelteLiteral"))
    return [attribute.value.map((item) => item.value).join("")];
  return expressionStrings(attribute?.value?.[0]?.expression);
}

function literalAttribute(node, name) {
  const attribute = node.startTag.attributes.find(
    (item) => item.type === "SvelteAttribute" && item.key.name === name
  );
  if (attribute?.value?.every((item) => item.type === "SvelteLiteral"))
    return attribute.value.map((item) => item.value).join("");
  const expression = attribute?.value?.[0]?.expression;
  return expression?.type === "Literal" && typeof expression.value === "string"
    ? expression.value
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
          specialized:
            'Use {{component}} instead of Input type="{{type}}"; a styled native field bypasses the shared control.',
        },
      },
      create(context) {
        const filename = context.filename.replaceAll("\\", "/");
        const baseline = nativeFieldBaseline.filter((item) => filename.endsWith("/" + item.file));
        const seen = new Map();
        const sharedInputs = new Set();
        const components = [];
        return {
          ImportDeclaration(node) {
            const source = String(node.source.value);
            if (!source.includes("components/ui")) return;
            for (const specifier of node.specifiers) {
              if (
                (specifier.type === "ImportDefaultSpecifier" && source.endsWith("/input.svelte")) ||
                (specifier.type === "ImportSpecifier" && specifier.imported.name === "Input")
              )
                sharedInputs.add(specifier.local.name);
              else if (specifier.type === "ImportNamespaceSpecifier")
                sharedInputs.add(`${specifier.local.name}.Input`);
            }
          },
          SvelteElement(node) {
            if (node.kind === "component") components.push(node);
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
            for (const component of components) {
              if (!sharedInputs.has(context.sourceCode.getText(component.name))) continue;
              for (const type of new Set(attributeStrings(component, "type"))) {
                const replacement = specializedInputTypes.get(type);
                if (replacement)
                  context.report({
                    node: component.startTag,
                    messageId: "specialized",
                    data: { type, component: replacement },
                  });
              }
            }
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
