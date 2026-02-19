"""
SPC Student IT Club - Google Sites Crawler
==========================================
Crawls all pages using Playwright (fully rendered HTML+CSS),
automatically discovers all internal links, saves each page
to a local folder ready to push to GitHub.

Requirements:
    py -m pip install playwright beautifulsoup4
    py -m playwright install chromium

Usage:
    py crawl.py
"""

import asyncio
import os
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

BASE_URL = "https://sites.google.com/view/spc-student-it-club"
START_PAGE = BASE_URL + "/home"
OUTPUT_DIR = "spc-site"

visited = set()


def is_internal(url):
    """Check if a URL belongs to the same Google Sites project."""
    return url.startswith(BASE_URL)


def url_to_filename(url):
    """Convert a Google Sites URL to a local html filename."""
    path = urlparse(url).path
    path = path.replace("/view/spc-student-it-club", "")
    path = path.strip("/").replace("/", "_")
    if not path:
        path = "home"
    return path + ".html"


def extract_internal_links(html, current_url):
    """Find all internal links on the page that we haven't visited yet."""
    soup = BeautifulSoup(html, "html.parser")
    links = set()
    for tag in soup.find_all("a", href=True):
        href = tag["href"]
        full = urljoin(current_url, href)
        # Strip query strings and fragments
        full = full.split("?")[0].split("#")[0]
        if is_internal(full) and full not in visited:
            links.add(full)
    return links


def rewrite_internal_links(html, current_url):
    """Rewrite internal Google Sites links to point to local .html files."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("a", href=True):
        href = tag["href"]
        full = urljoin(current_url, href).split("?")[0].split("#")[0]
        if is_internal(full):
            tag["href"] = url_to_filename(full)
    return str(soup)


async def crawl_page(browser, url):
    """Open a page in headless Chromium, grab fully rendered HTML+CSS."""
    filename = url_to_filename(url)
    print(f"  Crawling: {url}")

    context = await browser.new_context(
        viewport={"width": 1280, "height": 900},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
    )
    page = await context.new_page()

    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
    except Exception:
        await page.wait_for_timeout(5000)

    # Extra wait for lazy content
    await page.wait_for_timeout(2000)

    # Capture all computed CSS
    styles = await page.evaluate("""() => {
        let css = '';
        for (const sheet of document.styleSheets) {
            try {
                for (const rule of sheet.cssRules) {
                    css += rule.cssText + '\\n';
                }
            } catch(e) {}
        }
        return css;
    }""")

    html_content = await page.content()
    await context.close()

    # Discover new internal links before rewriting
    new_links = extract_internal_links(html_content, url)

    # Parse and process HTML
    soup = BeautifulSoup(html_content, "html.parser")

    # Remove external stylesheet links (we inline everything)
    for link in soup.find_all("link", rel="stylesheet"):
        link.decompose()

    # Inject captured CSS inline
    style_tag = soup.new_tag("style")
    style_tag.string = styles
    if soup.head:
        soup.head.append(style_tag)

    # Base tag so CDN asset URLs still resolve correctly
    base_tag = soup.new_tag("base", href="https://sites.google.com")
    if soup.head:
        soup.head.insert(0, base_tag)

    # Rewrite internal links to local files
    final_html = rewrite_internal_links(str(soup), url)

    # Save file
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(final_html)

    print(f"  Saved:    {filepath}")
    return new_links


async def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"\nSPC IT Club Crawler")
    print(f"===================")
    print(f"Output folder: {OUTPUT_DIR}/\n")

    # Queue of pages to crawl
    queue = {START_PAGE}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        while queue:
            url = queue.pop()
            if url in visited:
                continue
            visited.add(url)

            new_links = await crawl_page(browser, url)

            # Add any newly discovered pages to the queue
            for link in new_links:
                if link not in visited:
                    print(f"  Found new page: {link}")
                    queue.add(link)

        await browser.close()

    # Rename home.html -> index.html for GitHub Pages
    home = os.path.join(OUTPUT_DIR, "home.html")
    index = os.path.join(OUTPUT_DIR, "index.html")
    if os.path.exists(home):
        os.rename(home, index)
        print(f"\nRenamed home.html -> index.html")

    print(f"\nDone! {len(visited)} pages saved to '{OUTPUT_DIR}/'")
    print(f"Push the '{OUTPUT_DIR}/' folder contents to your GitHub Pages repo.")


if __name__ == "__main__":
    asyncio.run(main())
