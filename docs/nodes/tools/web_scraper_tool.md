# Web Scraper

## What is it?

The Web Scraper tool is a utility that can be given to an agent to help it extract information from web pages.

## When would I use it?

Use this node when you want to:

- Enable agents to extract data from websites
- Scrape content from web pages
- Gather information from online sources
- Automate web data collection

## How to use it

### Basic Setup

1. Add the Web Scraper tool to your workflow
1. Connect its output to nodes that need web scraping capabilities (like an Agent)

### Outputs

- **tool**: The configured web scraper tool that other nodes can use

## Example

Imagine you want to create an agent that can scrape web content:

1. Add a Web Scraper tool to your workflow
1. Connect the "tool" output to an Agent's "tools" input
1. Now that agent can perform web scraping operations when needed in conversations

## Implementation Details

The Web Scraper tool is implemented using Griptape's `WebScraperTool` class and provides a simple interface for extracting content from web pages. The tool is designed to be used by agents to gather information from websites in a structured way.

## Important Notes

- The tool respects website terms of service and robots.txt files
- Performance may vary depending on the structure and complexity of websites
- Some websites may block automated scraping attempts
- The tool works best with text-based content rather than dynamic JavaScript-heavy sites
- Consider rate limiting and ethical use to avoid overloading websites

## Common Issues

- **Access Denied**: Some websites actively block web scrapers
- **Content Not Found**: Dynamic content loaded via JavaScript might not be accessible
- **Rate Limiting**: Excessive requests may trigger rate limiting from websites
- **Changing Layouts**: Website structure changes can affect scraping reliability
- **Processing Large Pages**: Very large web pages may take longer to process or exceed token limits
