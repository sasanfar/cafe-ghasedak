#!/usr/bin/env python3
"""Incrementally sync new Cafe Ghasedak Blogfa posts into this repository.

Existing post files are identified by their ``post_id`` frontmatter field. New
posts are downloaded with their currently public comments, written to
``YEAR/MONTH/TITLE.md``, and added to the chronological index. Public comments
are also checked for every archived post and newly seen comments are appended.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from lxml import etree
from lxml import html as lhtml


DEFAULT_BASE_URL = "https://cafe-ghasedak.blogfa.com"
USER_AGENT = "Mozilla/5.0 (compatible; Cafe-Ghasedak-Archive/1.0)"
FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
EN_TO_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
MONTHS = {
    "فروردین": 1,
    "اردیبهشت": 2,
    "خرداد": 3,
    "تیر": 4,
    "مرداد": 5,
    "شهریور": 6,
    "مهر": 7,
    "آبان": 8,
    "آذر": 9,
    "دی": 10,
    "بهمن": 11,
    "اسفند": 12,
}
FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
COMMENTS_HEADING = "## دیدگاه‌ها"


@dataclass
class Comment:
    author: str
    date_text: str
    body_html: str
    url: str | None = None


@dataclass
class Post:
    post_id: int
    listed_title: str | None = None
    source_url: str = ""
    title: str = ""
    content_html: str = ""
    date_text: str = ""
    year: int = 0
    month: int = 0
    day: int = 0
    author: str = ""
    comments: list[Comment] = field(default_factory=list)
    relpath: PurePosixPath | None = None


class SyncError(RuntimeError):
    """Raised when the remote archive cannot be synchronized safely."""


def fetch(url: str, retries: int = 5) -> bytes:
    """Fetch a public page with small retries for transient CDN errors."""
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept-Language": "fa,en;q=0.8",
                },
            )
            with urllib.request.urlopen(request, timeout=45) as response:
                data = response.read()
            if not data:
                raise SyncError("empty response")
            return data
        except Exception as exc:  # urllib exposes several transient error types
            last_error = exc
            time.sleep(1.0 + attempt * 1.5)
    raise SyncError(f"Could not fetch {url}: {last_error}")


def normalized_text(node) -> str:
    return re.sub(r"\s+", " ", node.text_content().replace("\xa0", " ")).strip()


def parse_frontmatter(path: Path) -> dict[str, object] | None:
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None

    result: dict[str, object] = {}
    for line in match.group(1).splitlines():
        key, separator, raw_value = line.partition(":")
        if not separator:
            continue
        key = key.strip()
        raw_value = raw_value.strip()
        if not key:
            continue
        if raw_value.startswith(('"', "'")):
            try:
                result[key] = json.loads(raw_value)
            except json.JSONDecodeError:
                result[key] = raw_value.strip("\"'")
        elif re.fullmatch(r"-?\d+", raw_value):
            result[key] = int(raw_value)
        elif raw_value in {"null", "~"}:
            result[key] = None
        else:
            result[key] = raw_value
    return result


def load_existing_posts(root: Path) -> dict[int, Post]:
    posts: dict[int, Post] = {}
    for path in root.rglob("*.md"):
        if ".git" in path.parts:
            continue
        metadata = parse_frontmatter(path)
        if not metadata or not isinstance(metadata.get("post_id"), int):
            continue

        post_id = int(metadata["post_id"])
        if post_id in posts:
            raise SyncError(
                f"Duplicate post_id {post_id} in {posts[post_id].relpath} and "
                f"{path.relative_to(root)}"
            )

        date_value = str(metadata.get("date", ""))
        date_match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", date_value)
        if not date_match:
            raise SyncError(f"Invalid or missing date frontmatter in {path.relative_to(root)}")

        year, month, day = map(int, date_match.groups())
        posts[post_id] = Post(
            post_id=post_id,
            title=str(metadata.get("title", "")).strip(),
            source_url=str(metadata.get("source", "")),
            date_text=str(metadata.get("date_text", "")),
            year=year,
            month=month,
            day=day,
            author=str(metadata.get("author", "")),
            relpath=PurePosixPath(path.relative_to(root).as_posix()),
        )
    return posts


def parse_post_list_page(raw: bytes, base_url: str) -> tuple[list[Post], int]:
    root = lhtml.fromstring(raw)
    posts: list[Post] = []
    for anchor in root.xpath('//div[@id="result"]/a[contains(@href, "/post/")]'):
        href = anchor.get("href", "")
        match = re.search(r"/post/(\d+)", href)
        if not match:
            continue
        raw_title = normalized_text(anchor)
        posts.append(
            Post(
                post_id=int(match.group(1)),
                listed_title=None if raw_title == "[عنوان ندارد]" else raw_title,
                source_url=urllib.parse.urljoin(base_url, href),
            )
        )

    pages = [1]
    for anchor in root.xpath('//div[contains(@class,"pagination")]//a[@href]'):
        match = re.search(r"[?&]p=(\d+)", anchor.get("href", ""))
        if match:
            pages.append(int(match.group(1)))
    return posts, max(pages)


def crawl_post_list(base_url: str) -> dict[int, Post]:
    first_url = f"{base_url}/posts/"
    first_posts, last_page = parse_post_list_page(fetch(first_url), base_url)
    if not first_posts:
        raise SyncError(f"No posts were found at {first_url}")

    posts = {post.post_id: post for post in first_posts}
    for page in range(2, last_page + 1):
        page_url = f"{base_url}/posts/?p={page}"
        page_posts, _ = parse_post_list_page(fetch(page_url), base_url)
        if not page_posts:
            raise SyncError(f"Post list page {page} was unexpectedly empty")
        posts.update({post.post_id: post for post in page_posts})
    return posts


def parse_comments(raw: bytes, base_url: str) -> list[Comment]:
    root = lhtml.fromstring(raw)
    comments: list[Comment] = []
    boxes = root.xpath(
        '//div[@id="content"]/div['
        'contains(concat(" ",normalize-space(@class)," ")," box ")]'
    )
    for box in boxes:
        author_nodes = box.xpath(
            './/div[contains(concat(" ",normalize-space(@class)," ")," author ")]'
        )
        date_nodes = box.xpath(
            './/div[contains(concat(" ",normalize-space(@class)," ")," date ")]'
        )
        body_nodes = box.xpath(
            './div[contains(concat(" ",normalize-space(@class)," ")," body ")]'
        )
        if not author_nodes or not body_nodes:
            continue

        author_node = author_nodes[0]
        link_nodes = author_node.xpath('.//a[@href]')
        commenter_url = (
            urllib.parse.urljoin(base_url, link_nodes[0].get("href"))
            if link_nodes
            else None
        )
        body_node = body_nodes[0]
        body_html = "".join(
            lhtml.tostring(child, encoding="unicode", method="html") for child in body_node
        )
        if body_node.text and body_node.text.strip():
            body_html = html.escape(body_node.text) + body_html
        comments.append(
            Comment(
                author=normalized_text(author_node),
                date_text=normalized_text(date_nodes[0]) if date_nodes else "",
                body_html=body_html,
                url=commenter_url,
            )
        )
    return comments


def parse_remote_post(summary: Post, base_url: str) -> Post:
    root = lhtml.fromstring(fetch(summary.source_url))
    post_nodes = root.xpath(
        '//div[contains(concat(" ",normalize-space(@class)," ")," post ")]'
    )
    if not post_nodes:
        raise SyncError(f"Post block missing for {summary.source_url}")
    block = post_nodes[0]

    heading = block.xpath('.//h2[1]')
    site_title = normalized_text(heading[0]) if heading else ""
    content_nodes = block.xpath(
        './/div[contains(concat(" ",normalize-space(@class)," ")," postcontent ")]'
    )
    if not content_nodes:
        raise SyncError(f"Post content missing for {summary.source_url}")
    content = content_nodes[0]
    for clear in content.xpath(
        './/*[contains(concat(" ",normalize-space(@class)," ")," clear ")]'
    ):
        clear.getparent().remove(clear)

    content_html = "".join(
        lhtml.tostring(child, encoding="unicode", method="html") for child in content
    )
    if content.text and content.text.strip():
        content_html = html.escape(content.text) + content_html

    info_nodes = block.xpath(
        './/div[contains(concat(" ",normalize-space(@class)," ")," postinfo ")]'
    )
    info = normalized_text(info_nodes[0]) if info_nodes else ""
    date_match = re.search(
        r"نوشته شده در\s+(.+?)\s+(\d{1,2})\s+"
        r"(فروردین|اردیبهشت|خرداد|تیر|مرداد|شهریور|مهر|آبان|آذر|دی|بهمن|اسفند)"
        r"\s+(\d{4})\s+ساعت\s*(.*?)\s+توسط\s+(.+?)(?:\s*\||$)",
        info.translate(FA_DIGITS),
    )
    if not date_match:
        raise SyncError(f"Could not parse post date for {summary.source_url}: {info!r}")

    weekday, day, month_name, year, _time_text, author = date_match.groups()
    post = Post(
        post_id=summary.post_id,
        listed_title=summary.listed_title,
        source_url=summary.source_url,
        title=site_title or summary.listed_title or "",
        content_html=content_html,
        date_text=f"{weekday} {int(day)} {month_name} {int(year)}".translate(EN_TO_FA_DIGITS),
        year=int(year),
        month=MONTHS[month_name],
        day=int(day),
        author=author.strip(),
    )

    comments_url = f"{base_url}/comments/?blogid=cafe-ghasedak&postid={post.post_id}"
    post.comments = parse_comments(fetch(comments_url), base_url)
    return post


def make_untitled_name(post: Post) -> str:
    fragment = lhtml.fragment_fromstring(
        f"<div>{post.content_html}</div>", create_parent=False
    )
    plain = normalized_text(fragment)
    plain = re.sub(r"^[\s\"'«»….,،؛:!?؟ـ-]+", "", plain)
    words = plain.split()
    candidate = " ".join(words[:8]).strip()
    if len(candidate) > 90:
        candidate = candidate[:90].rsplit(" ", 1)[0]
    return candidate or f"نوشته {post.post_id}"


def safe_filename(title: str) -> str:
    title = title.replace("/", "⁄").replace("\\", "⧵")
    title = re.sub(r'[<>:"|?*\x00-\x1f]', "", title)
    return title.rstrip(". ").strip() or "بدون عنوان"


def yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def normalize_internal_id(href: str, source_url: str) -> int | None:
    absolute = urllib.parse.urljoin(source_url, href)
    parsed = urllib.parse.urlparse(absolute)
    host = parsed.netloc.lower().split(":")[0]
    if host not in {"cafe-ghasedak.blogfa.com", "www.cafe-ghasedak.blogfa.com"}:
        return None
    match = re.search(r"/(?:post/|post-)(\d+)(?:/|\.aspx|$)", parsed.path, re.I)
    return int(match.group(1)) if match else None


def clean_external_href(href: str, source_url: str) -> str:
    absolute = urllib.parse.urljoin(source_url, href)
    parsed = urllib.parse.urlparse(absolute)
    if parsed.netloc.lower().endswith("blogfa.com") and parsed.path == "/r":
        target = urllib.parse.parse_qs(parsed.query).get("url")
        if target:
            return target[0]
    return absolute


def rewrite_links(fragment_html: str, post: Post, by_id: dict[int, Post]) -> str:
    wrapper = lhtml.fragment_fromstring(
        f"<div>{fragment_html}</div>", create_parent=False
    )
    assert post.relpath is not None
    for anchor in wrapper.xpath('.//a[@href]'):
        href = anchor.get("href", "")
        target_id = normalize_internal_id(href, post.source_url)
        if target_id is not None and target_id in by_id:
            target = by_id[target_id]
            assert target.relpath is not None
            relative = os.path.relpath(
                str(target.relpath.with_suffix(".html")), start=str(post.relpath.parent)
            ).replace(os.sep, "/")
            anchor.set("href", urllib.parse.quote(relative, safe="/()[]-_.~"))
        else:
            anchor.set("href", clean_external_href(href, post.source_url))

    for image in wrapper.xpath('.//img[@src]'):
        image.set("src", urllib.parse.urljoin(post.source_url, image.get("src")))

    for element in wrapper.iter():
        for attribute in (
            "style",
            "class",
            "lang",
            "dir",
            "width",
            "height",
            "border",
            "align",
        ):
            element.attrib.pop(attribute, None)
    etree.strip_tags(wrapper, "span", "font")

    return "".join(
        ([html.escape(wrapper.text)] if wrapper.text else [])
        + [
            lhtml.tostring(child, encoding="unicode", method="html")
            for child in wrapper
        ]
    )


def html_to_markdown(fragment: str) -> str:
    if not shutil.which("pandoc"):
        raise SyncError("pandoc is required but was not found on PATH")
    process = subprocess.run(
        ["pandoc", "-f", "html", "-t", "gfm", "--wrap=none"],
        input=fragment,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        raise SyncError(f"pandoc failed: {process.stderr.strip()}")
    markdown = process.stdout.replace("\u00a0", " ")
    return re.sub(r"\n{3,}", "\n\n", markdown).strip()


def assign_new_paths(new_posts: list[Post], existing: dict[int, Post]) -> None:
    occupied = {
        str(post.relpath).casefold()
        for post in existing.values()
        if post.relpath is not None
    }
    base_names = [
        (post.year, post.month, safe_filename(post.title)) for post in new_posts
    ]
    new_name_counts = Counter(base_names)

    for post in sorted(new_posts, key=lambda item: item.post_id):
        filename = safe_filename(post.title)
        relative = PurePosixPath(f"{post.year:04d}") / f"{post.month:02d}" / f"{filename}.md"
        if (
            str(relative).casefold() in occupied
            or new_name_counts[(post.year, post.month, filename)] > 1
        ):
            filename = f"{filename} — {post.post_id}"
            relative = (
                PurePosixPath(f"{post.year:04d}")
                / f"{post.month:02d}"
                / f"{filename}.md"
            )
        if str(relative).casefold() in occupied:
            raise SyncError(f"Could not choose a unique path for post {post.post_id}")
        post.relpath = relative
        occupied.add(str(relative).casefold())


def render_post(post: Post, by_id: dict[int, Post], base_url: str) -> str:
    assert post.relpath is not None
    source = f"{base_url}/post/{post.post_id}/"
    frontmatter = [
        "---",
        f"title: {yaml_quote(post.title)}",
        f"date: {yaml_quote(f'{post.year:04d}-{post.month:02d}-{post.day:02d}')}",
        f"date_text: {yaml_quote(post.date_text)}",
        f"post_id: {post.post_id}",
        f"author: {yaml_quote(post.author)}",
        f"source: {yaml_quote(source)}",
        "---",
        "",
        f"# {post.title}",
        "",
    ]
    body = html_to_markdown(rewrite_links(post.content_html, post, by_id))
    parts = ["\n".join(frontmatter), body]

    comments_section = render_comments_section(post, post.comments, by_id)
    if comments_section:
        parts.extend(["", comments_section])
    return "\n".join(parts).rstrip() + "\n"


def render_comments_section(
    post: Post, comments: list[Comment], by_id: dict[int, Post]
) -> str:
    if not comments:
        return ""
    return "\n\n".join(
        [COMMENTS_HEADING, render_comment_entries(post, comments, by_id, start=1)]
    ).rstrip()


def render_comment_entries(
    post: Post,
    comments: list[Comment],
    by_id: dict[int, Post],
    start: int,
) -> str:
    parts: list[str] = []
    for index, comment in enumerate(comments, start=start):
        parts.append(f"### {index}. {comment.author or 'ناشناس'}")
        parts.append("")
        if comment.date_text:
            parts.append(f"- زمان: {comment.date_text}")
        if comment.url:
            parts.append(f"- لینک: [{comment.url}]({comment.url})")
        if comment.date_text or comment.url:
            parts.append("")
        parts.append(
            html_to_markdown(rewrite_links(comment.body_html, post, by_id))
        )
        parts.append("")
    return "\n".join(parts).rstrip()


def archived_comment_count(markdown: str) -> int:
    marker = f"\n{COMMENTS_HEADING}\n"
    if marker not in markdown:
        return 0
    _body, _separator, comments = markdown.rpartition(marker)
    return len(re.findall(r"^###\s+\d+\.\s", comments, flags=re.MULTILINE))


def archived_comment_keys(markdown: str) -> Counter[tuple[str, str]]:
    marker = f"\n{COMMENTS_HEADING}\n"
    if marker not in markdown:
        return Counter()
    _body, _separator, comments = markdown.rpartition(marker)
    blocks = re.split(r"^###\s+\d+\.\s+", comments, flags=re.MULTILINE)[1:]
    keys: Counter[tuple[str, str]] = Counter()
    for block in blocks:
        lines = block.splitlines()
        author = lines[0].strip() if lines else "ناشناس"
        date_match = re.search(r"^- زمان:\s*(.*?)\s*$", block, flags=re.MULTILINE)
        date_text = date_match.group(1).strip() if date_match else ""
        keys[(author, date_text)] += 1
    return keys


def add_new_comments(
    markdown: str,
    post: Post,
    comments: list[Comment],
    by_id: dict[int, Post],
) -> str | None:
    """Return updated Markdown only when previously unseen comments exist.

    Existing entries are matched as an author/date multiset. New live entries
    are appended, while comments removed from the website remain archived.
    """
    current_count = archived_comment_count(markdown)
    archived_keys = archived_comment_keys(markdown)
    missing: list[Comment] = []
    for comment in comments:
        key = (comment.author or "ناشناس", comment.date_text)
        if archived_keys[key] > 0:
            archived_keys[key] -= 1
        else:
            missing.append(comment)
    if not missing:
        return None

    marker = f"\n{COMMENTS_HEADING}\n"
    new_entries = render_comment_entries(
        post, missing, by_id, start=current_count + 1
    )
    if marker in markdown:
        return f"{markdown.rstrip()}\n\n{new_entries}\n"
    else:
        body = markdown.rstrip()
        return f"{body}\n\n{COMMENTS_HEADING}\n\n{new_entries}\n"


def fetch_existing_comments(
    posts: dict[int, Post], base_url: str
) -> dict[int, list[Comment]]:
    def fetch_one(post_id: int) -> tuple[int, list[Comment]]:
        url = f"{base_url}/comments/?blogid=cafe-ghasedak&postid={post_id}"
        return post_id, parse_comments(fetch(url), base_url)

    results: dict[int, list[Comment]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(fetch_one, post_id): post_id for post_id in posts}
        for future in concurrent.futures.as_completed(futures):
            post_id = futures[future]
            try:
                result_id, comments = future.result()
            except Exception as exc:
                raise SyncError(f"Failed to fetch comments for post {post_id}: {exc}") from exc
            results[result_id] = comments
    return results


def render_index(posts: dict[int, Post]) -> str:
    ordered = sorted(
        posts.values(), key=lambda post: (post.year, post.month, post.day, post.post_id)
    )
    lines = [
        "---",
        'title: "فهرست زمانی کافه قاصدک"',
        "---",
        "",
        "# فهرست زمانی کافه قاصدک",
        "",
        "مرتب‌شده از قدیمی‌ترین به جدیدترین.",
        "",
    ]
    current_year: int | None = None
    for post in ordered:
        if post.year != current_year:
            current_year = post.year
            lines.extend([f"## {current_year}", ""])
        assert post.relpath is not None
        label = f"{post.year:04d}-{post.month:02d}-{post.day:02d} — {post.title}"
        href = urllib.parse.quote(
            str(post.relpath.with_suffix(".html")), safe="/()[]-_.~"
        )
        lines.append(f"- [{label}]({href})")
    return "\n".join(lines).rstrip() + "\n"


def update_heartbeat(root: Path, interval_days: int, dry_run: bool) -> bool:
    if interval_days <= 0:
        return False
    path = root / ".github" / "blog-sync-heartbeat"
    today = dt.datetime.now(dt.timezone.utc).date()
    previous: dt.date | None = None
    if path.exists():
        try:
            previous = dt.date.fromisoformat(path.read_text(encoding="utf-8").strip())
        except ValueError:
            previous = None
    if previous is not None and (today - previous).days < interval_days:
        return False
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(today.isoformat() + "\n", encoding="utf-8")
    return True


def sync(root: Path, base_url: str, dry_run: bool, heartbeat_days: int) -> int:
    existing = load_existing_posts(root)
    remote = crawl_post_list(base_url)
    missing_ids = sorted(set(remote) - set(existing))

    new_posts: list[Post] = []
    if missing_ids:
        workers = min(4, len(missing_ids))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            future_by_id = {
                pool.submit(parse_remote_post, remote[post_id], base_url): post_id
                for post_id in missing_ids
            }
            for future in concurrent.futures.as_completed(future_by_id):
                post_id = future_by_id[future]
                try:
                    post = future.result()
                except Exception as exc:
                    raise SyncError(f"Failed to parse new post {post_id}: {exc}") from exc
                post.title = post.title.strip() or make_untitled_name(post)
                new_posts.append(post)

        new_posts.sort(key=lambda post: post.post_id)
        assign_new_paths(new_posts, existing)

    all_posts = dict(existing)
    all_posts.update({post.post_id: post for post in new_posts})

    # New posts already include comments from parse_remote_post. Check every
    # older post as well so late comments are added beneath the original note.
    live_existing_comments = fetch_existing_comments(existing, base_url)
    comment_updates: dict[int, str] = {}
    for post_id, post in existing.items():
        assert post.relpath is not None
        path = root / Path(*post.relpath.parts)
        current_markdown = path.read_text(encoding="utf-8")
        updated_markdown = add_new_comments(
            current_markdown,
            post,
            live_existing_comments[post_id],
            all_posts,
        )
        if updated_markdown is not None:
            comment_updates[post_id] = updated_markdown

    if not dry_run:
        for post in new_posts:
            assert post.relpath is not None
            destination = root / Path(*post.relpath.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                render_post(post, all_posts, base_url), encoding="utf-8"
            )

        for post_id, markdown in comment_updates.items():
            post = existing[post_id]
            assert post.relpath is not None
            path = root / Path(*post.relpath.parts)
            path.write_text(markdown, encoding="utf-8")

        index_path = root / "فهرست.md"
        expected_index = render_index(all_posts)
        current_index = (
            index_path.read_text(encoding="utf-8") if index_path.exists() else ""
        )
        if expected_index != current_index:
            index_path.write_text(expected_index, encoding="utf-8")

    heartbeat_changed = update_heartbeat(root, heartbeat_days, dry_run)
    if new_posts:
        print(f"Added {len(new_posts)} new post(s):")
        for post in new_posts:
            print(f"  {post.post_id}: {post.relpath}")
    else:
        print(f"Archive is up to date ({len(existing)} posts).")
    if comment_updates:
        print(f"Updated comments in {len(comment_updates)} existing post(s):")
        for post_id in sorted(comment_updates):
            print(f"  {post_id}: {existing[post_id].relpath}")
    else:
        print("No new comments were found on existing posts.")
    if heartbeat_changed:
        print("Updated the scheduled-workflow heartbeat.")
    return len(new_posts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Archive repository root (defaults to the parent of scripts/)",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Blog base URL (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report new posts without modifying files",
    )
    parser.add_argument(
        "--heartbeat-days",
        type=int,
        default=0,
        help="Refresh .github/blog-sync-heartbeat after this many days (0 disables)",
    )
    arguments = parser.parse_args()

    try:
        sync(
            root=arguments.root.resolve(),
            base_url=arguments.base_url.rstrip("/"),
            dry_run=arguments.dry_run,
            heartbeat_days=arguments.heartbeat_days,
        )
    except SyncError as exc:
        print(f"sync error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
