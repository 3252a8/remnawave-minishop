import re

with open('bot/app/web/templates/subscription_webapp.html', 'r', encoding='utf-8') as f:
    html = f.read()

long_classes = set(re.findall(r'class="([^"]{40,})"', html))
for cls in long_classes:
    print(f"--- LONG CLASS ({len(cls)} chars) ---\n{cls}\n")
