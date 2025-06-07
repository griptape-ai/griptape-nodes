# Scrape Web

## What is it?

The Scrape Web tool is a utility that allows you to extract text content from web pages.

## When would I use it?

Use this node when you want to:

- Extract text content from specific web pages
- Gather information from websites
- Collect data from online sources
- Automate web content extraction

## How to use it

### Basic Setup

1. Add the Scrape Web tool to your workflow
1. Configure the scraping parameters
1. Connect its output to nodes that need the scraped content

### Parameters

- **url**: The URL of the web page to scrape

### Outputs

- **output**: The text content extracted from the web page

## Example

Imagine you want to extract content from a specific web page:

1. Add a Scrape Web tool to your workflow
1. Set the URL of the page you want to scrape
1. Connect the "output" to another node that needs the scraped content

## Implementation Details

The Scrape Web tool uses web scraping capabilities to extract text content from web pages. It can target specific content using CSS selectors and handles timeouts and errors gracefully.
