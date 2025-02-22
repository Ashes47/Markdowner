from pyppeteer import launch
from markdown_utils import convert_html_to_markdown
import os
import asyncio
import requests
from functools import lru_cache

# Global persistent browser instance
browser = None
semaphore = asyncio.Semaphore(4)  # Limit to 4 concurrent requests

async def get_browser():
    """Initialize Puppeteer browser session if not already running."""
    global browser
    if browser is None:
        browser = await launch(
            executablePath=os.getenv("PUPPETEER_EXECUTABLE_PATH", "/usr/bin/chromium"),
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
    return browser

async def auto_scroll(page):
    """
    Scrolls down the page to force lazy-loaded content to appear.
    Stops if no new content loads after multiple attempts.
    """
    await page.evaluate("""
        async () => {
            await new Promise((resolve) => {
                let lastHeight = document.body.scrollHeight;
                let attempts = 0;
                
                const scrollInterval = setInterval(() => {
                    window.scrollBy(0, window.innerHeight * 0.8);  // Large chunk scrolling
                    
                    let newHeight = document.body.scrollHeight;
                    if (newHeight === lastHeight) {
                        attempts += 1;
                    } else {
                        attempts = 0;  // Reset if new content loads
                    }

                    lastHeight = newHeight;
                    
                    // Stop if no new content appears after 3 attempts
                    if (attempts >= 3) {
                        clearInterval(scrollInterval);
                        resolve();
                    }
                }, 500);
            });
        }
    """)


async def fetch_page_content(url: str) -> str:
    """Fetch page content using Puppeteer with concurrency control."""
    async with semaphore:  # Limit concurrent page processing
        browser = await get_browser()
        page = await browser.newPage()
        try:
            await page.goto(url, {"waitUntil": "networkidle2", "timeout": 60000})
            await page.waitForSelector("main, body", timeout=10000)
            await auto_scroll(page)
            content = await page.content()
            return convert_html_to_markdown(content, url)
        except Exception as e:
            return f"⚠️ Error: Failed to process {url}\n{str(e)}"
        finally:
            await page.close()  # Ensure page is closed properly

async def convert_website_to_markdown(url: str, crawl_subpages: bool = False, subpage_limit: int = 10) -> str:
    """Converts website or tweet to Markdown. Handles subpage crawling dynamically."""
    
    # **🟢 Check if URL is a Tweet**
    if "twitter.com" in url or "x.com" in url:
        tweet_id = url.rstrip("/").split("/")[-1]
        if not tweet_id.isnumeric():
            raise ValueError("Invalid tweet URL")

        # Fetch tweet content as Markdown
        return await get_tweet_markdown(tweet_id)

    # **🟢 Process Regular Webpages using Puppeteer**
    markdown_content = await fetch_page_content(url)

    if crawl_subpages:
        links = await extract_links(url)
        subpage_tasks = [convert_website_to_markdown(link, False) for link in links[:subpage_limit]]
        subpage_markdowns = await asyncio.gather(*subpage_tasks)
        markdown_content += "\n\n".join(subpage_markdowns)

    return markdown_content

async def extract_links(url: str):
    """Extract all subpage links from the given URL."""
    browser = await get_browser()
    page = await browser.newPage()
    try:
        await page.goto(url, {"waitUntil": "networkidle2"})
        links = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('a')).map(link => link.href);
        }""")
        return links
    except Exception:
        return []
    finally:
        await page.close()  # Ensure page is closed


@lru_cache(maxsize=100)
def get_tweet_data(tweet_id: str):
    """Fetch and cache Twitter API responses for faster performance."""
    url = f"https://cdn.syndication.twimg.com/tweet-result?id={tweet_id}&lang=en&token=4c2mmul6mnh"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0",
        "TE": "Trailers"
    }
    
    response = requests.get(url, headers=headers, timeout=5)
    if response.status_code == 200:
        return response.json()
    return None


async def get_tweet_markdown(tweet_id: str) -> str:
    """Fetches and formats a tweet as Markdown using Twitter Syndication API."""
    
    tweet_data = get_tweet_data(tweet_id)

    if not tweet_data:
        return "⚠️ Error: Unable to fetch tweet."
    
    # Extract tweet details safely
    user_name = tweet_data.get("user", {}).get("name", "Unknown User")
    screen_name = tweet_data.get("user", {}).get("screen_name", "unknown")
    text = tweet_data.get("text", "No tweet content found.")
    created_at = tweet_data.get("created_at", "Unknown Date")
    like_count = tweet_data.get("favorite_count", "N/A")
    retweet_count = tweet_data.get("conversation_count", "N/A")

    # Handle images if present
    image_urls = [img["url"] for img in tweet_data.get("photos", [])] if "photos" in tweet_data else []
    images_md = "\n".join(f"![Image]({url})" for url in image_urls) if image_urls else "No images"

    # Format the tweet as Markdown
    return f"""
    **Tweet from [{user_name} (@{screen_name})](https://twitter.com/{screen_name}/status/{tweet_id})**

    📝 {text}

    📅 Date: {created_at}  
    👍 Likes: {like_count}  
    🔁 Retweets: {retweet_count}

    📷 Images:  
    {images_md}
    """
