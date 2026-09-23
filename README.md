# کافه قاصدک

آرشیو نوشته‌ها با قالب اختصاصی فارسی و راست‌به‌چپ، ساخته‌شده با Jekyll برای GitHub Pages.

## انتشار

در **Settings → Pages** این ریپو، **Deploy from a branch**، شاخهٔ **main** و پوشهٔ **/(root)** را انتخاب کنید. پس از انتشار، سایت در `https://sasanfar.github.io/cafe-ghasedak/` در دسترس است. انتشار بعدی با هر push به `main` انجام می‌شود.

## افزودن نوشته

فایل Markdown را در پوشهٔ `سال/ماه/` بگذارید و فرادادهٔ `title`، `date_text` و `post_id` را مانند نوشته‌های موجود بنویسید. صفحهٔ اصلی، آرشیو و پیوند نوشتهٔ قبلی و بعدی به صورت خودکار از همین فراداده ساخته می‌شوند؛ لازم نیست فهرست صفحهٔ اصلی را دستی ویرایش کنید. برای ترتیب درست، `post_id` باید عددی و یکتا باشد.

## اجرای محلی

با Ruby و Jekyll نصب‌شده:

```sh
gem install github-pages
jekyll serve --baseurl /cafe-ghasedak
```

قالب در `_layouts/` و `_includes/`، ظاهر در `assets/css/style.css` و جست‌وجوی عنوان‌ها در `assets/js/archive.js` قرار دارد.
