# Medium2Dev

A command-line tool to convert Medium posts to DEV.to markdown format and optionally publish them directly to DEV.to as draft posts.

## Features

- Converts Medium articles to DEV.to compatible markdown
- Preserves headings, formatting, and text structure
- Downloads and properly references inline images
- Removes Medium-specific UI elements and metadata
- Fixes code link formatting
- Generates appropriate frontmatter for DEV.to
- Optionally publishes directly to DEV.to as a draft post
- Provides word count comparison between Medium and DEV.to versions
- Simple command-line interface

## Installation

```bash
# Clone the repository
git clone https://github.com/awsdataarchitect/medium2dev.git
cd medium2dev

# Install dependencies
pip install -r requirements.txt
```

## Usage

```bash
# Basic conversion
python3 medium2dev.py https://medium.com/your-article-url

# Specify output directory
python3 medium2dev.py https://medium.com/your-article-url -o /path/to/output

# Specify image directory
python3 medium2dev.py https://medium.com/your-article-url -i /path/to/images

# Publish directly to DEV.to as a draft
python3 medium2dev.py https://medium.com/your-article-url --publish --api-key YOUR_DEVTO_API_KEY

# Or use environment variable for API key
export DEVTO_API_KEY=your_api_key
python3 medium2dev.py https://medium.com/your-article-url --publish
```

## Example

```bash
python3 medium2dev.py https://medium.com/aws-in-plain-english/aws-resource-tag-compliance-with-automation-64ae16e42a11
```

This will:
1. Download the Medium article
2. Extract all content and images
3. Convert to DEV.to compatible markdown
4. Save the markdown file and images to the specified directories

When using the `--publish` flag, the tool will also:
1. Publish the article as a draft to DEV.to
2. Display a word count comparison between Medium and DEV.to versions

## Requirements

- Python 3.6+
- requests
- beautifulsoup4
- html2text

## License

MIT
