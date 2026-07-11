# Meridian

A personal news PWA. Feeds are fetched every 2 hours by a GitHub Action
(scripts/fetch_feeds.py -> data/feed.json) and served via GitHub Pages.
Interest learning happens entirely client-side in localStorage.

- Live app: https://nyrlnd.github.io/meridian/
- To refresh feeds manually: Actions tab -> "Fetch feeds" -> Run workflow
- Note: GitHub pauses scheduled workflows after ~60 days of repo inactivity;
  running the workflow manually re-enables the schedule.
