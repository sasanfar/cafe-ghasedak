---
title: خانه
---

{% assign writings = site.pages | where_exp: "item", "item.post_id" | sort: "post_id" | reverse %}
{% assign latest = writings.first %}

<section class="hero" aria-labelledby="hero-title">
  <div class="hero-copy">
    <span class="eyebrow"><span class="eyebrow-line"></span> درِ کافه باز است</span>
    <h1 id="hero-title">کافه <em>قاصدک</em></h1>
    <p class="hero-lead">جایی میان عطر قهوه، صدای صفحه و کلماتی که هنوز زنده‌اند.</p>
    <p class="hero-small">از اولین فنجان تا امروز؛ نوشته‌هایی برای مکث کردن، خواندن و دوباره برگشتن.</p>
    <div class="hero-actions">
      {% if latest %}<a class="button button-primary" href="{{ latest.url | relative_url }}">تازه‌ترین نوشته <span aria-hidden="true">←</span></a>{% endif %}
      <a class="button button-outline" href="{{ '/archive/' | relative_url }}">دیدن همهٔ نوشته‌ها</a>
    </div>
  </div>
  <div class="hero-art" aria-hidden="true">
    <div class="art-caption">CAFE · GHASEDAK <span>✦</span> EST. 1388</div>
    <div class="record"><div class="record-label"><span>کافه</span><span>قاصدک</span><small>۳۳⅓ RPM</small></div></div>
    <div class="record-arm"></div>
    <div class="coffee"><div class="coffee-top"></div><div class="coffee-handle"></div><div class="coffee-saucer"></div></div>
    <span class="art-note">یک فنجان، یک قصه، یک صفحه...</span>
  </div>
</section>

<section class="latest section-wrap" aria-labelledby="latest-title">
  <div class="section-heading">
    <div><span class="section-kicker">تازه از کافه</span><h2 id="latest-title">آخرین نوشته‌ها</h2></div>
    <a class="text-link" href="{{ '/archive/' | relative_url }}">آرشیو کامل <span aria-hidden="true">←</span></a>
  </div>
  <div class="story-grid">
    {% for post in writings limit:9 %}
    <article class="story-card">
      <div class="card-top"><span class="card-number">{{ forloop.index | prepend: '0' | slice: -2, 2 }}</span><span class="card-flourish" aria-hidden="true">✳</span></div>
      <div class="story-meta">{{ post.date_text | default: post.date }} <span aria-hidden="true">·</span> فنجان {{ post.post_id }}</div>
      <h3><a href="{{ post.url | relative_url }}">{{ post.title | escape }}</a></h3>
      <a class="card-read" href="{{ post.url | relative_url }}" aria-label="خواندن {{ post.title | escape }}">ادامهٔ نوشته <span aria-hidden="true">←</span></a>
    </article>
    {% endfor %}
  </div>
</section>

<section class="years-band" aria-labelledby="years-title">
  <div class="section-wrap years-inner">
    <div><span class="section-kicker">ورق زدن زمان</span><h2 id="years-title">از آن سال‌ها تا امروز</h2><p>هر سال، چند فنجان خاطره.</p></div>
    <div class="year-links">
      {% assign last_year = '' %}
      {% for post in writings %}
        {% assign year = post.path | slice: 0, 4 %}
        {% if year != last_year %}<a href="{{ '/archive/' | relative_url }}#year-{{ year }}">{{ year }}</a>{% assign last_year = year %}{% endif %}
      {% endfor %}
    </div>
  </div>
</section>
