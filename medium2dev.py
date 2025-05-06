#!/usr/bin/env python3
"""
Medium2Dev - Convert Medium posts to DEV.to markdown format and optionally publish to DEV.to
"""

import argparse
import os
import re
import requests
import sys
import json
import logging
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import html2text
import time

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('medium2dev')

class Medium2Dev:
    def __init__(self, url, output_dir=None, image_dir=None, api_key=None):
        """Initialize the converter with the Medium post URL."""
        self.url = url
        self.output_dir = output_dir or os.getcwd()
        self.image_dir = image_dir or os.path.join(self.output_dir, 'images')
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.medium_word_count = 0
        
        # Create image directory if it doesn't exist
        if not os.path.exists(self.image_dir):
            os.makedirs(self.image_dir)
            
    def fetch_article(self):
        """Fetch the Medium article content."""
        logger.info(f"Fetching article from {self.url}")
        try:
            # Add headers to mimic a browser request
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Referer': 'https://medium.com/',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Cache-Control': 'max-age=0'
            }
            
            response = self.session.get(self.url, headers=headers)
            response.raise_for_status()
            
            # Check if we need to handle a JavaScript redirect
            if 'window.location.href' in response.text:
                # Extract the redirect URL
                match = re.search(r'window\.location\.href\s*=\s*"([^"]+)"', response.text)
                if match:
                    redirect_url = match.group(1)
                    logger.info(f"Following redirect to {redirect_url}")
                    response = self.session.get(redirect_url, headers=headers)
                    response.raise_for_status()
            
            return response.text
        except requests.RequestException as e:
            logger.error(f"Error fetching article: {e}")
            sys.exit(1)
    
    def extract_content(self, html_content):
        """Extract the article content from the HTML."""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extract title
        title_tag = soup.find('h1')
        title = title_tag.text.strip() if title_tag else "Untitled Article"
        
        # Extract publication date for frontmatter only
        date_tag = soup.find('meta', property='article:published_time')
        date = date_tag['content'].split('T')[0] if date_tag else ""
        
        # Extract article content
        article_tag = soup.find('article')
        if not article_tag:
            # Try alternative selectors for Medium content
            article_tag = soup.select_one('div.section-content')
            
        if not article_tag:
            # Try another approach - find the main content div
            article_tag = soup.find('div', class_='postArticle-content')
            
        if not article_tag:
            logger.error("Could not find article content")
            sys.exit(1)
            
        # Create a new div to hold only the content we want
        content_div = soup.new_tag('div')
        
        # Find all the content sections (paragraphs, headings, code blocks, images)
        # Make sure to include all header levels (h1-h6)
        content_elements = article_tag.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'pre', 'figure', 'img', 'blockquote', 'ul', 'ol', 'div'])
        
        # Add the content elements to our new div
        for element in content_elements:
            # Skip elements that are likely part of the author byline or metadata
            if element.name not in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6'] and any(cls in str(element.get('class', [])) for cls in ['postMetaLockup', 'graf--authorName', 'authorLockup']):
                continue
                
            # Skip elements with author info, claps, etc.
            if element.name not in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6'] and element.find(string=re.compile(r'clap|follow|min read|sign up|bookmark|Listen|Share')):
                continue
                
            # Skip elements that just contain "--" or numbers at the beginning
            if element.name == 'p' and re.match(r'^\s*--\s*$|^\s*\d+\s*$', element.text.strip()):
                continue
                
            # Skip the title (h1) since we'll add it in the frontmatter
            if element.name == 'h1' and element.text.strip() == title:
                continue
                
            # Skip elements that contain "In Plain English" footer
            if element.name not in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6'] and element.find(string=re.compile(r'In Plain English|Thank you for being a part of')):
                continue
                
            # Skip elements that just contain "·" character
            if element.name == 'p' and element.text.strip() == '·':
                continue
                
            content_div.append(element)
            
        # Calculate the word count of the original content
        content_text = ' '.join([element.get_text() for element in content_div.contents])
        self.medium_word_count = len(content_text.split())
        logger.info(f"Original Medium content word count: {self.medium_word_count}")
            
        return {
            'title': title,
            'date': date,
            'content': content_div
        }
    
    def download_images(self, content):
        """Download images and update their references in the content."""
        images = content.find_all('img')
        downloaded_count = 0
        
        for i, img in enumerate(images):
            if not img.get('src'):
                continue
                
            # Get image URL
            img_url = img['src']
            if not img_url.startswith(('http://', 'https://')):
                img_url = urljoin(self.url, img_url)
            
            # Skip small profile images and icons (typically < 100px)
            if 'resize:fill:64:64' in img_url or 'resize:fill:88:88' in img_url:
                img.decompose()  # Remove author profile images
                continue
                
            # For Medium images, try to get the full-size version
            if 'miro.medium.com' in img_url:
                # Remove size constraints from URL to get original image
                img_url = re.sub(r'/resize:[^/]+/', '/', img_url)
                # Remove query parameters that might limit image size
                img_url = img_url.split('?')[0]
            
            # Generate image filename with a more descriptive name
            img_extension = os.path.splitext(urlparse(img_url).path)[1]
            if not img_extension:
                img_extension = '.jpg'  # Default extension
                
            img_filename = f"image_{i+1}{img_extension}"
            img_path = os.path.join(self.image_dir, img_filename)
            
            # Create image directory if it doesn't exist
            if not os.path.exists(self.image_dir):
                os.makedirs(self.image_dir)
            
            # Download image
            try:
                logger.info(f"Downloading image: {img_url}")
                img_response = self.session.get(img_url, stream=True)
                img_response.raise_for_status()
                
                with open(img_path, 'wb') as f:
                    for chunk in img_response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                # Update image reference in content
                img_relative_path = os.path.join('images', img_filename)
                img['src'] = img_relative_path
                downloaded_count += 1
                
            except requests.RequestException as e:
                logger.warning(f"Failed to download image {img_url}: {e}")
        
        logger.info(f"Downloaded {downloaded_count} content images")        
        return content
    
    def convert_to_markdown(self, content):
        """Convert HTML content to Markdown format suitable for DEV.to."""
        # Process content before conversion
        for pre in content.find_all('pre'):
            # Ensure code blocks are properly formatted
            if pre.find('code'):
                pre['class'] = 'highlight'
                
        for figure in content.find_all('figure'):
            # Handle figure captions
            figcaption = figure.find('figcaption')
            if figcaption:
                img = figure.find('img')
                if img:
                    img['alt'] = figcaption.text.strip()
        
        # Remove Medium-specific UI elements and metadata
        for element in content.select('.postMetaLockup, .graf--pullquote, .section-divider, .js-actionMultirecommendCount, .js-actionRecommend'):
            if element:
                element.decompose()
        
        # Remove share buttons, claps, and other interactive elements
        for element in content.select('button, .buttonSet, .js-actionRecommend, .js-postMetaLockup'):
            if element:
                element.decompose()
                
        # Convert to markdown
        h2t = html2text.HTML2Text()
        h2t.body_width = 0  # Don't wrap lines
        h2t.ignore_links = False
        h2t.ignore_images = False
        h2t.ignore_emphasis = False
        h2t.ignore_tables = False
        
        markdown = h2t.handle(str(content))
        
        # Post-process markdown
        # Fix code blocks
        markdown = re.sub(r'```\n\s*```', '', markdown)
        
        # Fix image paths
        def repl(match):
            path = match.group(1)
            if path.startswith('images/'):
                return f"![Image]({path})"
            return match.group(0)
            
        markdown = re.sub(r'!\[.*?\]\((.*?)\)', repl, markdown)
        
        # Fix headings (ensure proper spacing)
        markdown = re.sub(r'(?<!\n)#{1,6} ', r'\n\g<0>', markdown)
        
        # Remove Medium-specific footer text and links
        markdown = re.sub(r'\n\s*\[.*?\]\(https?://medium\.com/.*?\)\s*\n', '\n\n', markdown)
        
        # Remove clap indicators and other Medium UI elements
        markdown = re.sub(r'\d+\s*claps?', '', markdown)
        markdown = re.sub(r'Follow\s*\d+\s*min read', '', markdown)
        
        # Remove "Listen" and "Share" text that often appears at the beginning
        markdown = re.sub(r'^\s*--\s*\n+\d+\s*\n+Listen\s*\n+Share\s*\n+', '', markdown)
        markdown = re.sub(r'^\s*--\s*\n+\d+\s*\n+', '', markdown)
        markdown = re.sub(r'^\s*·\s*\n+', '', markdown)
        markdown = re.sub(r'^\s*\\--\s*\n+', '', markdown)
        
        # Fix code links format - change `[text](url)` to [`text`](url)
        markdown = re.sub(r'`\[(.*?)\]\((.*?)\)`', r'[`\1`](\2)', markdown)
        
        # Remove Medium footer about "In Plain English" community
        markdown = re.sub(r'# In Plain English.*?$', '', markdown, flags=re.DOTALL)
        markdown = re.sub(r'_Thank you for being a part of the_.*?$', '', markdown, flags=re.DOTALL)
        
        # Remove author links at the beginning
        markdown = re.sub(r'^\s*\[\]\(https://.*?medium\.com/.*?\)\s*\n+', '', markdown)
        markdown = re.sub(r'^\s*\[Vivek V\]\(https://.*?medium\.com/.*?\)\s*\n+', '', markdown)
        
        # Clean up multiple blank lines
        markdown = re.sub(r'\n{3,}', '\n\n', markdown)
        
        # Remove any remaining "·" and "--" at the beginning of the document
        lines = markdown.split('\n')
        while lines and (lines[0].strip() == '·' or lines[0].strip() == '--' or lines[0].strip() == '\\--'):
            lines.pop(0)
        markdown = '\n'.join(lines)
        
        # Final cleanup of any remaining "--" characters
        markdown = re.sub(r'\n\\--\n', '\n\n', markdown)
        markdown = re.sub(r'\n--\n', '\n\n', markdown)
        
        return markdown
    
    def generate_frontmatter(self, title, date):
        """Generate DEV.to frontmatter."""
        # Extract tags from the URL or use default tags
        tags = ["aws", "tutorial", "programming"]  # Default tags
        
        # Try to extract tags from URL path components
        parsed_url = urlparse(self.url)
        path_components = parsed_url.path.strip('/').split('/')
        if len(path_components) > 1:
            # The first component might be a publication name or topic
            potential_tag = path_components[0].replace('-', '')
            if potential_tag and potential_tag not in ['medium', 'blog', 'posts']:
                # Ensure tag is alphanumeric only
                potential_tag = re.sub(r'[^a-zA-Z0-9]', '', potential_tag)
                if potential_tag:
                    tags.insert(0, potential_tag)
        
        frontmatter = [
            "---",
            f"title: {title}",
            f"published: false",  # Set to false for draft
            f"date: \"{date}\"",  # Date in quotes to ensure proper formatting
            f"tags: {json.dumps(tags)}",
            f"canonical_url: \"{self.url}\"",  # URL in quotes to handle special characters
            "cover_image: ",
            "---\n"
        ]
        
        return "\n".join(frontmatter)
    
    def convert(self):
        """Convert the Medium post to DEV.to markdown format."""
        html_content = self.fetch_article()
        extracted = self.extract_content(html_content)
        
        # Download images
        processed_content = self.download_images(extracted['content'])
        
        # Convert to markdown
        markdown_content = self.convert_to_markdown(processed_content)
        
        # Generate frontmatter
        frontmatter = self.generate_frontmatter(
            extracted['title'], 
            extracted['date']
        )
        
        # Combine frontmatter and content
        full_markdown = frontmatter + "\n" + markdown_content
        
        # Generate output filename
        parsed_url = urlparse(self.url)
        slug = parsed_url.path.strip('/').split('/')[-1]
        output_filename = f"{slug}.md"
        output_path = os.path.join(self.output_dir, output_filename)
        
        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(full_markdown)
            
        logger.info(f"Conversion complete! Output saved to {output_path}")
        return output_path, extracted['title'], full_markdown
    
    def publish_to_devto(self, title, markdown_content):
        """Publish the converted markdown as a draft post to DEV.to."""
        if not self.api_key:
            logger.error("No DEV.to API key provided. Skipping publish.")
            return False
            
        logger.info("Publishing to DEV.to as draft...")
        
        api_url = "https://dev.to/api/articles"
        headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json"
        }
        
        # Extract frontmatter to properly format the article data
        frontmatter_match = re.match(r'---\n(.*?)\n---\n', markdown_content, re.DOTALL)
        body_markdown = markdown_content
        
        # Prepare the article data
        article_data = {
            "article": {
                "title": title,
                "body_markdown": body_markdown,
                "published": False  # Set as draft
            }
        }
        
        try:
            response = requests.post(api_url, headers=headers, json=article_data)
            response.raise_for_status()
            article_data = response.json()
            logger.info(f"Successfully published draft to DEV.to! URL: https://dev.to/dashboard/drafts")
            return True
        except requests.RequestException as e:
            logger.error(f"Error publishing to DEV.to: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response: {e.response.text}")
            return False

def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description='Convert Medium posts to DEV.to markdown format and optionally publish as draft')
    parser.add_argument('url', help='URL of the Medium post to convert')
    parser.add_argument('-o', '--output-dir', help='Directory to save the output markdown file')
    parser.add_argument('-i', '--image-dir', help='Directory to save downloaded images')
    parser.add_argument('-p', '--publish', action='store_true', help='Publish to DEV.to as draft')
    parser.add_argument('-k', '--api-key', help='DEV.to API key (if not set via DEVTO_API_KEY environment variable)')
    
    args = parser.parse_args()
    
    # Get API key from environment or command line
    api_key = args.api_key or os.environ.get('DEVTO_API_KEY')
    
    # Check if publishing is requested but no API key is available
    if args.publish and not api_key:
        logger.error("Publishing requested but no DEV.to API key provided. Set DEVTO_API_KEY environment variable or use --api-key.")
        sys.exit(1)
    
    converter = Medium2Dev(args.url, args.output_dir, args.image_dir, api_key)
    output_path, title, markdown_content = converter.convert()
    
    print(f"\nConversion successful! Output saved to: {output_path}")
    print(f"Images saved to: {converter.image_dir}")
    
    # Calculate DEV.to word count
    devto_word_count = len(re.sub(r'---.*?---\n', '', markdown_content, flags=re.DOTALL).split())
    
    if args.publish:
        if converter.publish_to_devto(title, markdown_content):
            print("Successfully published as draft to DEV.to!")
            print("\nWord Count Comparison:")
            print("| Platform | Word Count |")
            print("|----------|------------|")
            print(f"| Medium   | {converter.medium_word_count} |")
            print(f"| DEV.to   | {devto_word_count} |")
        else:
            print("Failed to publish to DEV.to. Check logs for details.")

if __name__ == '__main__':
    main()
