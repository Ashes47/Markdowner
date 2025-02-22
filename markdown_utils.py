from markdownify import markdownify
from bs4 import BeautifulSoup
from htmlmin import minify
from urllib.parse import urljoin

def extract_images(soup, base_url):
    """
    Extracts images from HTML with improved handling:
    - Resolves relative URLs
    - Handles lazy-loaded images (`data-src`, `srcset`)
    - Includes `alt` text and `title` attributes for better context

    Args:
        soup (BeautifulSoup): Parsed HTML content.
        base_url (str): The base URL for resolving relative paths.

    Returns:
        list: A list of dictionaries with image data.
    """
    images = []
    
    for img in soup.find_all("img"):
        # Check possible image sources
        img_url = img.get("src") or img.get("data-src") or img.get("srcset")
        
        if img_url:
            # Resolve relative paths
            full_url = urljoin(base_url, img_url) if not img_url.startswith(("http", "//")) else img_url
            
            # Collect image metadata
            images.append({
                "url": full_url,
                "alt": img.get("alt", "No alt text"),
                "title": img.get("title", "No title")
            })

    return images


def cleanup_html(html_content: str, base_url: str) -> tuple:
    """
    Cleans up HTML content by:
    - Removing unnecessary tags (script, style)
    - Extracting title, links, and images
    - Minifying the HTML for efficiency
    - Converting cleaned content to Markdown

    Args:
        html_content (str): The raw HTML content.
        base_url (str): The base URL for resolving relative links.

    Returns:
        tuple: (title, markdown_content, link_list, image_list)
    """

    soup = BeautifulSoup(html_content, "html.parser")

    # Extract Page Title
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else f"URL: {base_url}"

    # Remove Unwanted Tags (Script & Style)
    for tag in soup(["script", "style", "noscript"]):
        tag.extract()

    # Extract Links
    links = [urljoin(base_url, a["href"]) for a in soup.find_all("a", href=True)]

    # Extract Images
    images = extract_images(soup, base_url)

    # Extract Cleaned Body Content
    body_content = soup.find("body")
    cleaned_html = minify(str(body_content)) if body_content else "No Body Content Found"

    # Convert to Markdown
    markdown_content = markdownify(cleaned_html)

    return title, markdown_content.strip(), links, images


def convert_html_to_markdown(html_content: str, base_url: str = "") -> str:
    """
    Converts HTML to a well-formatted Markdown representation.
    
    Args:
        html_content (str): The raw HTML content.
        base_url (str, optional): Base URL for resolving relative links.

    Returns:
        str: Well-structured Markdown output.
    """

    title, markdown_content, links, images = cleanup_html(html_content, base_url)

    # Format Markdown with Title, Links & Images
    markdown_output = f"# {title}\n\n{markdown_content}\n"

    if links:
        markdown_output += "\n## 🔗 Links\n" + "\n".join(f"- [{link}]({link})" for link in links)

    if images:
        markdown_output += "\n\n## 🖼️ Images\n" + "\n".join(f"![Image]({img})" for img in images)

    return markdown_output.strip()
