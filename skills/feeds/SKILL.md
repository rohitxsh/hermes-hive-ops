---
name: feeds
description: Use before web-searching for news, releases, announcements or regulatory updates that a feed may already cover, and when asked to follow or subscribe to a site.
version: 0.1.0
author: Rohit Shrivastava (rohitxsh), Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [rss, news, releases, monitoring, research]
---

# Feeds (Miniflux)

Miniflux is a self-hosted feed reader that polls every subscribed feed every 30 minutes. The `feeds` command reads it with no model calls and no web search. Check it first whenever the answer may already be in a feed: release notes, exchange or IPO announcements, index changes, government notifications, blogs and changelogs you follow.

```bash
feeds new --category Releases        # what arrived since this profile last looked (first use: last 24 h)
feeds new --peek                     # look without moving your cursor
feeds search "price band" --category IPO
feeds list                           # categories and feeds (failing feeds are marked)
feeds add https://example.com/feed.xml --category Releases
feeds filter 3 --block "(?i)canary|nightly"   # skip noisy entries by title (--keep REGEX keeps only matches)
feeds remove 3                       # unsubscribe a dead, duplicate or useless feed
```

Miniflux is for the agents only: nobody reads it by hand. Keep it useful for everyone on it. Add what helps, filter what's noisy, remove what's dead or never used, and tell your channel in one line what you changed.

- `new` keeps a cursor per profile and category, so each entry shows up once for you. Other profiles and VMs have their own cursors; nothing is marked read for anyone else.
- Entries come with a 300-character snippet. Open the URL with `web_extract` only when you need the full text.
- Searching the web is still right for facts no feed covers, or to confirm a detail a feed entry left out.
- Adding, filtering and removing feeds is routine. Feeds are shared across every VM, so remove only feeds you're sure nobody uses (check `feeds list` and ask with `consult` if another profile added it). To follow a page that has no feed, ask the owner to add a changedetection.io watch and subscribe to its RSS output.
- If `feeds` says the credential is missing or Miniflux can't be reached, say so once and fall back to web search.
