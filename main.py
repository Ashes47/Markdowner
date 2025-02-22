import asyncio
import redis
import os
import aiofiles
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, ORJSONResponse
from fastapi.templating import Jinja2Templates
from services import auto_scroll, convert_website_to_markdown
from services import get_browser

# Initialize FastAPI
app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Connect to Redis
redis_client = redis.Redis(host="redis", port=6379, decode_responses=True)

@app.get("/", response_class=ORJSONResponse)
async def home(request: Request):
    """Serve the HTML page."""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/convert", response_class=ORJSONResponse)
async def convert(url: str, crawl_subpages: bool = False, subpage_limit: int = 10):
    """Convert a website to Markdown, storing results in Redis for faster retrieval."""
    try:
        # Check if the Markdown already exists in Redis
        cached_markdown = redis_client.get(f"{url}_{crawl_subpages}_{subpage_limit}")
        if cached_markdown:
            return ORJSONResponse(content={
                "url": url,
                "markdown": cached_markdown,
                "file": f"/download?file={hash(url)}.md",
                "cached": True
            })

        # Convert the website to Markdown
        markdown_content = await convert_website_to_markdown(url, crawl_subpages, subpage_limit)

        # Store result in Redis (expire in 1 hour)
        redis_client.setex(f"{url}_{crawl_subpages}_{subpage_limit}", 3600, markdown_content)

        # Save Markdown to a file
        file_hash = hash(url)
        file_path = f"/tmp/{file_hash}.md"

        async with aiofiles.open(file_path, "w") as file:
            await file.write(markdown_content)

        return ORJSONResponse(content={
            "url": url,
            "markdown": markdown_content,
            "file": f"/download?file={file_hash}.md",
            "cached": False 
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download")
async def download(file: str):
    """Allows users to download the Markdown file."""
    file_path = f"/tmp/{file}"
    if os.path.exists(file_path):
        return FileResponse(file_path, filename=file)
    raise HTTPException(status_code=404, detail="File not found")

@app.on_event("shutdown")
async def shutdown():
    """Shutdown Puppeteer when FastAPI stops."""
    browser = await get_browser()
    await browser.close()


@app.get("/screenshot", response_class=ORJSONResponse)
async def take_screenshot(url: str):
    """Capture a full-page screenshot of the given URL."""
    try:
        # Check if cached screenshot exists
        screenshot_path = f"/tmp/{hash(url)}.png"
        if os.path.exists(screenshot_path):
            return ORJSONResponse(content={"url": url, "screenshot": f"/download_screenshot?file={hash(url)}.png"})

        # Launch Puppeteer
        browser = await get_browser()
        page = await browser.newPage()

        try:
            await page.goto(url, {"waitUntil": "networkidle2", "timeout": 60000})
            await auto_scroll(page)  # Scroll to ensure full content loads
            asyncio.sleep(2)
            await page.screenshot({"path": screenshot_path, "fullPage": True})  # Full-page screenshot

        finally:
            await page.close()

        return ORJSONResponse(content={"url": url, "screenshot": f"/download_screenshot?file={hash(url)}.png"})
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download_screenshot")
async def download_screenshot(file: str):
    """Download the screenshot file."""
    file_path = f"/tmp/{file}"
    if os.path.exists(file_path):
        return FileResponse(file_path, filename=file)
    raise HTTPException(status_code=404, detail="Screenshot not found")