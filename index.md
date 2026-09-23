---
layout: default
title: کافه قاصدک
---

# کافه قاصدک

نوشته‌ها، از جدیدترین به قدیمی‌ترین.

{% assign writings = site.pages | where_exp: "p", "p.post_id" | sort: "post_id" %}

{% for post in writings reversed %}
- **{{ post.date_text }}** — [{{ post.title }}]({{ post.url | relative_url }})
{% endfor %}
