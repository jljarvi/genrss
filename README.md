# Generous - genrss

Generate RSS from HTML.

## Overview

A Python script that extracts metadata and links from an HTML page and generates an RSS feed using the RSS 2.0 standard. It aims to be as verbose as possible, including metadata like Open Graph (_og:*_) and Twitter (_twitter:*_), images, descriptions, and publication dates (when available).

## Installation

```bash
uv sync
. ./.env
```

## Usage

```bash
uv run src/app.py <url>
```

## File structure

```bash
.
├── data
│   └── <domain>.json   # JSON file containing the data on existing RSS entries for the given domain
├── feeds
│   └── <domain>.xml    # RSS feed for the given domain
├── .env                # Environment variables
├── pyproject.toml      # Project configuration
├── README.md           # This file
└── src
    ├── app.py          # Main script
    ├── __init__.py     # Package initialisation
```

## Disclaimer

This is a personal project, and, as such, is probably too tightly coupled to my specific needs: so far, I've generated decent feeds for [Ollama](https://ollama.com/blog) and [Big Sister](https://bigsister.live/blog).

I'm sure there are plenty of edge cases that are not handled, and I'm also sure that the code could be improved.

If you have any suggestions, please open an issue or submit a PR.