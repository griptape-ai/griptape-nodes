# WebScraper

## What is it?

The WebScraper tool arguments an agent, allowing that agent to extract and process information from websites.

## When would I use it?

Use this node when you want to:

- Enable your agents to access and extract information from web pages
- Gather data from online sources for analysis
- Incorporate web content into your AI workflows
- Research information available on public websites
- Monitor web content for specific information

## How to use it

### Basic Setup

1. Add the WebScraper tool to your worksflow
1. Connect the "tool" output to an agent or other node that can utilize tools

### Parameters

- **off_prompt**: Whether to run web scraping operations outside the main prompt (default is False)

### Outputs

- **tool**: The configured web scraper tool that can be used by other nodes

## Example

Imagine you want to create an agent that can research information from websites:

1. Add a WebScraper to your workflow
1. Set the "name" parameter to "WebResearcher"
1. Set "off_prompt" to True for more efficient processing
1. Connect the "tool" output to an Agent's "tools" input
1. Now your agent can scrape and analyze web content when prompted

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
