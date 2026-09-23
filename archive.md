---
title: آرشیو نوشته‌ها
permalink: /archive/
---

{% assign writings = site.pages | where_exp: "item", "item.post_id" | sort: "post_id" | reverse %}
<section class="archive-header section-wrap">
  <span class="section-kicker">تمام فنجان‌ها</span>
  <h1>آرشیو کافه</h1>
  <p>از تازه‌ترین نوشته به سوی اولین فنجان. میان عنوان‌ها بگرد یا سالی را انتخاب کن.</p>
  <label class="search-label" for="story-search">جست‌وجو در عنوان‌ها</label>
  <div class="search-box"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="10.8" cy="10.8" r="6.4"/><path d="m16 16 5 5"/></svg><input id="story-search" type="search" placeholder="مثلاً قاصدک، باران، ۱۳۹۰..." autocomplete="off"></div>
  <p id="search-status" class="search-status" role="status" aria-live="polite"></p>
</section>

<div class="archive-layout section-wrap">
  <nav class="archive-years" aria-label="رفتن به سال">
    <span>سال‌ها</span>
    {% assign last_year = '' %}
    {% for post in writings %}
      {% assign year = post.path | slice: 0, 4 %}
      {% if year != last_year %}<a href="#year-{{ year }}">{{ year }}</a>{% assign last_year = year %}{% endif %}
    {% endfor %}
  </nav>
  <div class="archive-list" id="archive-list">
    {% assign last_year = '' %}
    {% for post in writings %}
      {% assign year = post.path | slice: 0, 4 %}
      {% if year != last_year %}{% unless forloop.first %}</div></section>{% endunless %}<section class="archive-group" id="year-{{ year }}"><h2><span>سال</span> {{ year }}</h2><div class="archive-entries">{% assign last_year = year %}{% endif %}
      <article class="archive-entry" data-search="{{ post.title | escape }} {{ post.date_text | escape }} {{ year }} {{ post.post_id }}"><span class="entry-date">{{ post.date_text | default: post.date }}</span><h3><a href="{{ post.url | relative_url }}">{{ post.title | escape }}</a></h3><span class="entry-arrow" aria-hidden="true">↖</span></article>
    {% endfor %}
    {% if writings.size > 0 %}</div></section>{% endif %}
  </div>
</div>
<script src="{{ '/assets/js/archive.js' | relative_url }}" defer></script>
