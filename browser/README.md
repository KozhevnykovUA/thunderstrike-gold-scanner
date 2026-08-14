# Browser-side BootyBayBroker collector

This collector exists because GitHub-hosted runners are blocked by Cloudflare while a normal user browser can access BootyBayBroker.

## One-shot collection

1. Open BootyBayBroker in a desktop browser and make sure the site itself loads normally.
2. Open DevTools -> Console.
3. Open `browser/bbb_collector.js` from this repository, copy all of it, paste it into the console and press Enter.
4. Wait a few seconds. The script makes polite same-origin requests using the browser's existing session, then downloads `bbb_snapshot.json`.
5. Put that file in the repository as `data/bbb_snapshot.json` (replace the old one if present).

A push of `data/bbb_snapshot.json` automatically triggers the scanner workflow. The workflow imports the snapshot, recalculates Enchanting route economics and disenchant thresholds, and commits generated reports.

## What it collects

The current basket includes Enchanting reagents, Superior Wizard Oil, and the core TBC Blacksmithing materials needed for the next optimizer phase. For each item the collector attempts to extract:

- lowest/current buyout
- market value / average
- available quantity
- auction count
- sale rate
- sold per day

The importer only overwrites prices for rows that were parsed successfully and have a current buyout. Failed rows leave the previous fallback value untouched.

## Security / behavior

The script does not solve or bypass Cloudflare challenges and does not contain credentials. It only runs after the user has opened BootyBayBroker normally and uses same-origin browser requests with that normal session. It does not need a GitHub token.
