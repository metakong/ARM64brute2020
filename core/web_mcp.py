import urllib.request
import urllib.parse
import json
import gc
import re
import sys
from html.parser import HTMLParser
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server named "OSINT_Node"
mcp = FastMCP("OSINT_Node")

class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
        self.ignore = False
        self.ignore_tags = ['script', 'style', 'header', 'footer', 'nav']

    def handle_starttag(self, tag, attrs):
        if tag in self.ignore_tags:
            self.ignore = True

    def handle_endtag(self, tag):
        if tag in self.ignore_tags:
            self.ignore = False

    def handle_data(self, data):
        if not self.ignore:
            content = data.strip()
            if content:
                self.text.append(content)

    def get_text(self):
        return " ".join(self.text)

def clean_html(html_content: str) -> str:
    parser = TextExtractor()
    parser.feed(html_content)
    return parser.get_text()

@mcp.tool()
def osint_scrape(query: str, max_urls: int = 3) -> str:
    """Performs a web search and extracts text content from the top results for OSINT analysis."""
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    # 1. Search DuckDuckGo Lite
    search_url = f"https://lite.duckduckgo.com/lite/?q={urllib.parse.quote(query)}"
    
    try:
        req = urllib.request.Request(search_url, headers={'User-Agent': user_agent})
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8')
        
        # 2. Extract links (Regex for Lite version result links)
        # Result links are usually in <a class="result-link" href="..."> or similar
        # In Lite, they are often inside <a class="result-link" href="...">
        links = re.findall(r'class="result-link" href="(https?://[^"]+)"', html)
        if not links:
            # Fallback for different Lite layouts
            links = re.findall(r'href="(https?://[^"]+)"', html)
            # Filter out DDG internal links
            links = [link for link in links if "duckduckgo.com" not in link][:max_urls]
        else:
            links = links[:max_urls]

        if not links:
            return f"No search results found for: {query}"

        # 3. Scrape and Extract
        results = []
        for url in links:
            try:
                print(f"[OSINT] Fetching: {url}", file=sys.stderr)
                req = urllib.request.Request(url, headers={'User-Agent': user_agent})
                with urllib.request.urlopen(req, timeout=10) as response:
                    content_type = response.headers.get('Content-Type', '')
                    if 'text/html' not in content_type:
                        continue
                    
                    page_html = response.read().decode('utf-8', errors='ignore')
                    text = clean_html(page_html)
                    # Truncate text to keep it manageable for LLM
                    results.append(f"SOURCE: {url}\nCONTENT: {text[:2000]}...")
            except Exception as e:
                results.append(f"SOURCE: {url}\nERROR: {str(e)}")
        
        output = "\n\n".join(results)
        return output if output else "Search completed but no content could be extracted."

    except Exception as e:
        return f"OSINT Node Error: {str(e)}"
    finally:
        gc.collect()

if __name__ == "__main__":
    mcp.run()
