# Ombra Detroit

A street-by-street shade map of downtown Detroit, Midtown, Corktown and the
riverfront, plus shade-aware walking routes. A port of Ombra Roma
(`ptrestler/ombra`), which it started as a copy of, history and all; that repo
is separate and nothing here should touch it.

Output is a **single self-contained HTML file** (~4.6 MB) with all data embedded:
no server, no network, works offline.

## Commands

```
pip install -r requirements.txt && npm install
npx playwright install chromium webkit    # both; make test needs WebKit too
make            # full build (data is cached, so ~10 min)
make artifact   # build/artifact.html, the file you publish as an Artifact
make test       # needs a build first; model + browser checks (Chromium, WebKit)
make heights    # height coverage, and every estimate scored against the tags; needs data/ only
make fetch      # the only target that needs the network; see "Where the data comes from"
make clean      # drop derived files, keep downloads
```

`make` rebuilds `dist/ombra-detroit.html`. The expensive stage is `shade.py`
(~7.5 min). Everything `make fetch` downloads is committed under `data/`.

## The city is `city.py`

Map area, projection origin and the sun's observer (the middle of the box), the
civil clock (`tz_for`, `dst_window`: the US rule, second Sunday of March to
first Sunday of November, −5/−4), the app's name, default units (miles), and
the data source. Every stage reads it; both builders fill the template's
`__APPNAME__`, `__CITY__`, `__TZNAME__`, `__UNITS__` tokens from it with
`city.fill`, and the payload carries the observer and clock (`head.proj`,
`head.place`) so the page's `cityTZ`/`solarPos` and `shade.py` cannot disagree.
The other city-specific things are names, never coordinates: the shortlist and
map labels in `places.py` (resolved against the data at build time; unmatched
names are printed and dropped), and the named-street fixtures in the tests.

## Where the data comes from

`city.SOURCE` picks one of two fetchers that write **the same files in the same
shape** (Overpass JSON: ways with tags and inline geometry), so nothing
downstream knows which it is reading:

- **`"overture"`** (current) — `fetch_overture.py` reads Overture Maps
  (release `2026-10-21.0`) from S3 with pyarrow, pushing the bbox down to the
  parquet statistics: about a minute. Writes `data/overture/`. Overture is OSM at
  its core (streets, outlines, water, parks, trees and fountains, with the
  original tags in `source_tags` for the base themes) plus building heights from
  Esri Community Maps, USGS lidar and Microsoft's ML buildings. DuckDB would be
  the obvious tool, but it downloads its S3 extension from a host the cloud
  sessions cannot reach; pyarrow needs nothing.
- **`"osm"`** — `fetch_osm.py`, straight from Overpass. Writes `data/osm/`
  (always, whatever `SOURCE` says). Raw tags, so it has what Overture drops.

What Overture does not carry, and so the current build does not have:
`opening_hours` (no church ships — see below), street `width` (every street
gets its class default), and wikipedia/wikidata on places (confidence ≥ 0.9 and
a category whitelist stand in; the named buildings are added as places because
in Detroit the building is often the destination).

## Pipeline

Each stage reads `build/` and writes `build/`. Paths always go through `paths.py`
so scripts run from any directory.

| stage | what it does | out |
|---|---|---|
| `fetch_overture.py` / `fetch_osm.py` | streets, buildings, building parts, water, greenery, trees, fountains, named places | `data/overture/` or `data/osm/` |
| `terrain.py` | elevation tiles → 10 m grid, map bbox + 2 km margin | `build/terr.npy` |
| `ground.py` | terrain smoothing (scored where the city has relief references), and the bare-earth check | `build/ground.npy` |
| `build_dsm.py` | 2 m raster of building + canopy height above ground | `build/dsm.npy` |
| `shade.py` | **the model.** 768 sun positions × ~28 k segments | `build/frames.npy` |
| `graph.py` | walking graph from segment geometry, junction-split | `build/graph.npz` |
| `places.py` | searchable destinations, shortlist, map labels | `build/places_pack.json` |
| `pack.py` | everything → one gzipped binary blob, base64 | `build/data.b64` |
| `build_standalone.py` | template + payload + document shell; the app's manifest, service worker and icons | `dist/` |
| `build_artifact.py` | template + payload, no shell — for publishing | `build/artifact.html` |

Supporting modules: `city.py`, `geo.py` (local metre projection), `solar.py`
(NOAA solar position), `hours.py` (OSM `opening_hours` → a schedule, or a
refusal), `heights.py` (OSM height tags → metres, and `estimate_untagged`, the
one rule for buildings without a height), `buildings.py` (the outlines and the
tower parts, shared by the build and the report), `streets.py` (segmentation).

Scripts that measure rather than build, none on the `make` path:
`measure_heights.py` (`make heights`) scores height coverage and every estimate
against the tagged heights; `compare_frames.py` diffs two `build/frames.npy`;
`measure_via.mjs`, `measure_boot.mjs`, `measure_dates.py` and `measure_days.mjs`
as described below. Their findings quoted in this file are Detroit's where they
were re-run for it and say "Rome" where they were not.

## How the shade model works

Street centrelines are cut into 40 m segments and sampled every 8 m. Each sample
is tested on **both sides** of the street, offset to where a sidewalk would be;
the reported number assumes you walk on the shadier side. From each sample a ray
is cast at the sun and tested against absolute surface elevation — `ground(q) +
object(q)` — starting from the observer's own ground height. In Rome that let
the Janiculum shadow Trastevere; Detroit is a river terrace (~18 m of relief,
p5–p95, across the whole grid), so here it is the towers that matter.

Frames are the 1st and 15th of each month, every 30 min from 06:00 to 21:30
(24 dates × 32 slots = 768). Times are Detroit civil time with the real US DST
dates. Every frame time is after the 02:00 switch, so a date is wholly on one
side of it.

## Things that will bite you

**`make test` needs a build first.** The Commands block above is in dependency
order, not a menu. On a fresh clone `build/` is empty, so `tests/validate.py`
has nothing to read and exits with `build it first: make`. Run `make` first.
`make clean` deliberately returns you to that state.

**Overpass mirrors are the worst part of this project, and from a cloud session
they are nearly all of it.** For Detroit: `overpass-api.de` resets every
connection from the session's IP within 2–3 s; `maps.mail.ru` answers but turns
most requests away with an instant 504; `overpass.kumi.systems` and
`overpass.private.coffee` connect and never send a byte. A cold fetch was on
course for 8 hours, which is why `city.SOURCE` is `"overture"`. Mirrors admit a
query by the timeout it declares, so `fetch_osm.py` declares short ones on small
tiles, retries 40 rounds with short backoff, and stops trying a mirror that
hangs twice without ever having answered. `overpass.osm.ch` answers with *zero
elements* rather than an error, which silently produces an empty map. A fetch
from a residential connection is the way to fill `data/osm/`; the tiles already
there are a partial fetch, kept because they are correct.

**`area=yes` ways are pedestrian plazas and must be included.** In Rome,
dropping them severed the walking network across ~300 squares (dead ends 17.9 %
→ 7.0 %, median detour 1.31 → 1.22 once included). Overture keeps them as
`land_use` areas of subtype `pedestrian`, not as streets, so `fetch_overture.py`
turns each one's outline into a `highway=pedestrian, area=yes` way (106 of them
here) — plazas are modelled as their **perimeter**, so routes walk round a
square, not across it.

**A street you may not walk on must not be in the network.** The
Detroit–Windsor Tunnel is a `primary` road under the river to Canada, and it
drew a red line into the water and gave the router a way across it. Overture
says `denied` for `foot` along its whole length; `fetch_overture.py` drops
every segment that does — 42 in this box, the tunnel's 4 among them, the rest
mostly freeway service drives.

**Towers are in `building:part`s, not in their outlines.** Downtown, the outline
round the Renaissance Center says little about its 222 m. Both fetchers take the
parts, `buildings.load(parts=True)` reads them, and `build_dsm.py` rasterises
outlines and parts together tallest-last, so each cell keeps the highest thing
over it. A part with `min_height` ≥ 3 m (a skybridge) goes into the surface but
not into "inside a building", or the street under it would read as indoors.
Parts are not buildings: they are in no count or report.

**`web/template.html` is not a valid HTML document and will look broken if you
open it directly.** It is written for the claude.ai Artifact wrapper, which
supplies the doctype, `<head>`, charset and viewport at publish time.
`build_standalone.py` adds a real document shell for the downloadable build.
Anything you test must be `dist/ombra-roma.html`.

**Don't use `DecompressionStream` to unpack the payload.** Some embedded web
views — iOS Quick Look among them — expose the Streams API but never resolve it,
so the page hangs on the loading screen with no error to catch. `ozInflate` in
`web/template.html` is a ~90-line DEFLATE decoder written inline for that reason;
it is verified byte-identical to zlib. Native `DecompressionStream` would not
have been faster anyway: on this payload in Chromium it took 529 ms where
`ozInflate` took 320 ms. There is also a `window.addEventListener('error')` handler that writes
failures onto the loading screen, so nothing fails silently again.

**Geolocation cannot work in the hosted artifact.** Artifacts render in a
cross-origin iframe, and geolocation's default allowlist is `self`, so it is off
unless the parent passes `allow="geolocation"`. Detect this **structurally**
(cross-origin parent, `isSecureContext`) — the previous version sniffed the
browser's error message for "policy", which is Chromium's wording, so Safari
fell through and wrongly told the user they had blocked location. Never assert a
cause the page cannot verify.

**A new thing on the map competes with the only thing it is for.** Two rules the
nasoni had to obey, and both were learned by putting 460 dots on the screen and
looking at it. *Colour is the shade ramp* — every hue on the map already means a
percentage, so a blue fountain reads as a shaded street. New marks are drawn in
`--ink` and `--panel`, with no hue of their own. *Density is measured, not
guessed* — the whole set is 382 dots on a 390×664 phone at the default zoom, one
per 678 px², which is not a map any more. `NASO_ZOOM` is 0.40 px/m because that
leaves about 45 of them on screen, and the number came from counting, not from
taste. The legend row appears and disappears with them, because a key for
something you cannot see is furniture.
Those counts are Rome's 460. Detroit has 14 mapped drinking fountains in the box,
so the threshold is generous here; it stays because the reasoning does.

**Overlay UI must be listed in `UIHIT`.** `#stage` captures pointer events for
pan/zoom; any panel not in that selector list gets its taps *also* treated as map
taps. This silently broke the route picker — selecting "Pantheon" set the start
to whatever street sat under the panel.

**The seven named streets in `tests/validate.py` are qualitative facts, not a
sensitivity test.** Bagley, Michigan and Grand River in the sun at 14:00 on
15 August; the Financial District canyons (Griswold, Shelby) shaded at 10:00;
Broadway, and Monroe in Greektown east of the towers, shaded at 18:00. They guard
the physics and the data wiring. When you touch the model, diff
`build/frames.npy` against the old one rather than trusting the named streets —
in Rome, scrambling the estimated heights moved 5.9 % of the map by more than
10 pp and the fixtures by at most 2 pp.

**Heights: 95 % are carried, and the 5 % that are estimated are not like the
rest — `make heights` is how you find out.** Of 4,888 buildings in the box,
4,608 carry a height from Overture (Esri Community Maps 3,325, USGS lidar 685,
Microsoft ML 330, OSM tags 268) and 25 a floor count only. The 255 left are
small — median footprint 27 m² against 220 m² for the tagged — so scoring an
estimate on *all* tagged buildings measures towers guessed from their
neighbours (IDW 10.32 m RMSE), which is not the job. On the 2,145 tagged
buildings with footprints like theirs (≤ 188 m²): IDW as shipped (k = 15,
≤ 500 m, clip 7–34 m) 4.18 m, unclipped 4.32, per-type defaults 7.13, a flat
5 m 4.61. So IDW stays, and `heights.INTERP_RMSE_M` is 4.18. Every number here
comes out of `measure_heights.py`, which calls `heights.estimate_untagged` — the
function the build runs. Never move one by eye.

The ML heights are the weak point, and nothing here measures them: they count as
carried, so the jitter probe does not move them. One Campus Martius, a mid-rise
office tower, reads 26 m. Overture keeps one height per building, so there is no
overlap between sources to score one against another; a raw OSM fetch would give
the tags to score Esri, lidar and ML against.

**`ground.py` checks bare earth, because a tower standing on itself would be
invisible.** In the US the AWS terrain tiles come from USGS 3DEP, which is bare
earth: under the 25 tallest tagged buildings (median 112 m) the ground reads
−0.06 m against the ground 50–100 m round them, and `validate.py` holds that
under 2 m. Rome's tiles were a surface model with the centro storico baked in
(+12 m); that is what the relief-pair scoring in `ground.py` was for, and it only
runs for a city that defines `RELIEF_POINTS`/`RELIEF_PAIRS`.

**The standalone is useless inside a document previewer, and that is not
fixable.** Opened from iOS Files (Quick Look) it suspends the JavaScript partway
and sits on the loading screen forever; opened from the Google Drive app it runs
the whole boot, paints the map correctly, and then hands you a letterboxed
static card that ignores every tap. Both look like bugs in the page and are not:
a canvas app needs live JavaScript *and* pointer events, and those viewers give
you at most one. iOS also will not open a local `.html` in Safari. So the
standalone is a desktop and offline build; **the hosted artifact is the answer
for a phone**, because it runs in a real browser.

**Never paint text with `rampFor`.** The ramp is built for thin lines over the
map; as 31 px numerals on a panel its middle disappears, and a route reading
73 % rendered as an indigo you could not make out against the dark card. Use
`rampInk`, which keeps the hue and walks it toward the panel's own text colour
until it clears 4.5:1 against *both* `--panel` and `--panel-2` — the route card
sits on one in the sidebar and the other on a phone. Note it returns
`rgb(r,g,b)` while the tokens are hex; mixing the two up is what made the first
attempt paint every number the same flat ink.

**The route panel resizes the map, so frame the map last.** On a phone the whole
console is hidden while the panel is up (`#app.routing`), which makes the map
area grow by about 250 px and shrink again on close; the picker on top of that
is a sheet over the lower 54 %. `setEnd` used to call `frameEnds` before it asked
the next question, so the start pin was centred for a layout that no longer
existed and landed under the sheet — visible in a screenshot, not visible on the
phone. Anything that measures `W`/`Hh` or `#rcard.offsetHeight` has to run after
the class changes, and every class change that moves the console has to call
`resize()`, or the canvas keeps the old size.

**Hiding the console took the clock with it, so the day strip had to become a
control.** It had always looked like one and been a hover readout — a
distinction a touchscreen cannot even express. With the console gone it was the
only way left to change the hour, so `bindStrip` now scrubs on tap and drag, and
previews only for a mouse that is passing over. That is also the better control
here: `#rstrip` plots the route's own shade through the day, so "worst 13:00" is
something you can act on. If you hide more of the console, check what else was
the only copy of something.

**A push can be live and still not be on the screen.** Pages serves
`index.html` with `Cache-Control: max-age=600` and gives no way to change that,
so for up to ten minutes a browser that already has the page keeps answering
from its own copy. Closing the tab is what fixes it. That cost two rounds of
"it's not there" over a button that was in every build, and the wrong conclusion
both times was that the deploy had failed. The page cannot beat the cache, so it
notices instead: `buildstamp.py` makes a time-and-commit string, both builders
stamp it into the template, the standalone writes the same string to
`dist/version.txt`, CI deploys the two together, and `checkFresh` fetches
`version.txt` with `no-store` on load and again whenever the tab comes back to
the front. If they disagree, a **Reload** pill appears. It only fetches on
http(s) — a `file://` copy cannot make that request, and what comes back is a
console error the browser logs before `.catch` ever sees it. The artifact is on
https and just 404s, which is the same as silence. So the prompt can only appear
where something deployed a `version.txt`, which is the only place it means
anything.

**Test in WebKit, not just Chromium.** Three separate bugs (the Streams hang, the
geolocation message, an unclickable close button behind a stacking context) were
invisible in Chromium. `npx playwright install webkit` if it is missing.
`tests/smoke.mjs` honours `PLAYWRIGHT_CHROMIUM_PATH` and `PLAYWRIGHT_WEBKIT_PATH`
for unusual installs; leave both unset unless you actually need them.

**The two "leaves the route most of the screen" checks read 49 % in a cloud
session, and that is the session, not the page.** Playwright's Chromium there
cannot load the webfonts, and the fallback runs taller. The last Rome build fails
the same two checks at 49 % in the same session and passed them in CI. CI, which
has the fonts, is the judge. A real 2 pp was found the same way, though: "No
drinking fountain within 40 m of this walk." pushed its button onto a second
line on most Detroit walks, because most of them pass no fountain — now "No
drinking fountain on this walk.", one line.

**Never `closePath` in a path with thousands of subpaths.** In Chromium it
costs time proportional to the path so far, so drawing every outline in one
path is quadratic: 2 k outlines 22 ms, 16 k 1,340 ms, 32 k 5,431 ms. `drawPolys`
did exactly that, and it was 1.15 s of a 1.7 s desktop boot — about 5 s of 7 on
a phone — and the same again on every whole-city redraw. Ending each outline
with `lineTo` back to its first point costs 4 ms at 16 k and fills identically,
because `fill` closes subpaths itself. Boot went from 1.7 s to 0.5 s, and at 4×
CPU from ~6.8 s to 2.0 s. It hid for so long because it is invisible zoomed in,
where culling leaves a few hundred outlines, and because nothing timed the
boot by stage: `measure_boot.mjs` does now.

**The Pages copy is an installable app, and nothing else is.** `build_standalone.py`
writes `manifest.webmanifest`, `sw.js` and `icons/` beside the page and puts
`<meta name="ombra-app">` in the standalone's head. `startApp()` only registers
the service worker and adds the manifest link when that meta is there *and* the
page came over http(s) — so not in the artifact (the platform's shell has no
meta) and not from a downloaded `file://` copy (no service worker can run, and a
static manifest link would be fetched and fail loudly). Three rules it depends on:

- *`sw.js` carries the build stamp.* That is how a browser learns of a deploy:
  Pages serves the page with `max-age=600`, but a service worker script is always
  revalidated. A build that left `sw.js` byte-identical would never update an
  installed copy.
- *The worker never takes over by itself.* It installs, waits, and the page shows
  the **Reload** pill; only the tap sends `skip`. Swapping the page under someone
  mid-walk would lose their route.
- *Installed, `checkFresh` asks the worker, not the page.* A reload would only
  serve the same cached build, so a newer `version.txt` triggers `update()`; if
  that finds nothing to install, the worker already holds the newer page (the
  HTTP cache served an old one on the way in) and the pill offers a plain reload.

`version.txt` always goes to the network, or no deploy could ever be seen. The
worker precaches with `cache: "no-cache"` — revalidate, so a first visit gets a
304 for the 6 MB it just downloaded and an update gets the new page rather than
the HTTP cache's ten-minute-old one. Playwright's WebKit runs no service workers,
so `tests/smoke.mjs` checks all of this in Chromium only: manifest and icon
sizes, install, control, an offline boot, and a deploy offered and taken.
If a broken build ever ships, an installed copy cannot show the pill that would
replace it — but the browser still fetches the next `sw.js` on launch, and a
waiting worker takes over once every window using the old one is closed. So the
fix for a bad deploy is another deploy, and "close the app and reopen it" is
what to tell anyone stuck on it.

**Today is answered with the closest sun, not the nearest date.** The model
samples the 1st and 15th; `measure_dates.py` scores ways of standing in for the
8th and 23rd of every month against their real shade. For Detroit: the nearest
sampled date at the same clock time is off by **3.00 pp** mean (3.91 % of
street-frames by more than 20), and **9.15 pp** for the dates whose brackets
straddle a clock change (early March, late October); the frame from *any* date
whose sun is closest in the sky, **1.49 pp** (1.91 %), 1.89 across the changes;
blending the two closest suns, 1.53. (Rome: 3.03, 12.9, 1.63, 1.67.) Shade
depends on the sun's direction and nothing else in this model. `solarPos` in the
template is `solar.py` line for line, and the smoke test holds it to the build's
own sun on all 768 frames (0.005° worst) and to `city.tz_for` on every one.
`sunAt(t)` is the one place a slot becomes a frame; it does not unpack shade,
`frameAt(t)` does. Choosing a month or the 1st/15th still shows that sampled date
exactly.

**Location, now and saved places are the installed app's, and each is
cautious in a specific way.** The dot is ink and panel like every other mark,
with a halo the size of the fix's accuracy. It starts by itself only where
permission is *already* granted — never a prompt at launch — and a fix far off
the map stops the GPS silently at launch and explains itself only when the
button asked. The clock follows real time (every 30 s, and on return to the
front) until the hour is moved by hand; moving the hour keeps today's date,
choosing a date leaves it, and **Back to now** restores both. Saved places are
stored as positions, not node numbers — every rebuild renumbers the nodes and a
saved hotel would quietly move — and matched back within 25 m.

**Churches are shown only where their hours can be read, and this build has
none.** Overture carries no `opening_hours`, so 0 of the 99 places of worship in
the box ship, the legend row stays hidden, and the methodology panel drops the
line rather than saying "0 of 99". The feature is intact for a raw-OSM build:
`hours.py` parses a deliberate subset at build time and *refuses* the rest (Rome:
59 of 63 tagged churches shipped). The smoke test still exercises the page's
church logic — open or closed by day and hour, the stop that will be shut when
you arrive, the tap — on one **fixture church** with the Pantheon's hours,
injected at Campus Martius when the data has none, and says so in its output.

**"Route via one" is scored on the dry stretch, not on the detour.** The
obvious rule — the fountain that adds least — chose one the walk already passed
97 % of the time: median detour 0 m, and every dry walk exactly as dry. The
minimax rule (shortest longer leg) ignores the fountains already on the way and
only moved the median dry stretch from 841 m to 776 m. What ships scores each
fountain as *longest dry stretch of the new walk + metres it adds*, both in
walked metres, so there is no weight to tune: 841 m → 581 m median, p90
1,412 m → 844 m, for a median 17 m more walking (Balanced, `node
measure_via.mjs`). "Metres added" can be negative — the stop can pull a
shade-weighted walk onto a shorter line. Two sweeps (from A, from B) give every
fountain both legs at once; candidates are tried in order of a lower bound on
their detour (crow-flies A→F→B, and cost/(1+k)) and stop when that alone loses,
which took Shadiest from 188 ms a recompute to 74 ms. The button only appears
where the dry-stretch line does, and the line must stay one line on a phone:
two pushes the card past half the map.
All of that is Rome's measurement, with 460 fountains. With 14, most Detroit
walks pass none, and a stop often adds distance without shortening the dry
stretch much (one test walk: +0.46 mi, dry stretch 1.85 → 1.82 mi).
`measure_via.mjs` has not been re-run for Detroit; whether the button earns its
line here is open.

**Stops are chained in the order you give them, and nothing reorders them.**
`measure_days.mjs` is why: the shadiest order is the shortest one on ~70 % of
days. The **+** under the swap button (up to six stops) turns a walk into
legs — it sits in that column because a row of its own cost every walk 30 px
and took the card past half the map; `recomputeChain` routes
each one at the half-hour it starts, walking 75 m/min and staying `st.stay`
minutes at each stop (the chip cycles 15–60), so the route keeps a frame per
edge (`st.route.efi`) and `drawOver` colours each leg at its own hour. A stop
has a field only while it is being chosen; after that it is a line in the
timeline (tap the name to change it, × to drop it), because two stops as
fields *and* lines took the card to 73 % of a phone and left the map 27 %. A
stop within 60 m of a church with readable hours says whether it will be open
when you get there. Pins are drawn over the place labels — a stop is usually
a landmark, and its own name used to sit on its number.
(Measured in Rome.)

## Publishing

- **<https://ptrestler.github.io/ombra-detroit/>** — GitHub Pages, deployed by
  the `deploy` job from the same build the tests ran against, on pushes to
  `main`. Pages has to be enabled for the repository (Settings → Pages → source:
  GitHub Actions) before the first deploy can land. A top-level HTTPS document,
  so the only hosted copy where **geolocation works**; deployed with a
  `version.txt`, a manifest, a service worker and icons, so it is **installable**
  and boots with no network.
- **`dist/ombra-detroit.html`** — the standalone. Not committed (base64 over
  gzip, no deltas); CI replaces a release asset on a fixed `build` tag instead:
  `https://github.com/ptrestler/ombra-detroit/releases/download/build/ombra-detroit.html`
- **`build/artifact.html`** — what gets published as a claude.ai Artifact. The
  platform wraps it in the document shell, so it carries no doctype or `<head>`.
  Never publish the standalone — the shells would nest.

**There is no Detroit artifact yet.** The URLs this file used to carry are
Ombra Roma's artifact; publishing to them would overwrite Rome with Detroit.
The first Detroit publish creates a new artifact — record its URL here. After
that, publishing is refused unless the session has read the live version first.

Sharing an artifact is *pinned to a version*: after a meaningful change, update
the pin from the share menu or the link keeps showing the old build. Signed out,
the URL serves the pinned version; check `document.querySelector('iframe').src`
(`.../_f/<version>/...`) before concluding a publish did not land.

## Payload format


Base64 lines in a `<script type="text/plain">`: one gzip blob, then one gzip
stream of shade per date. The blob is `[uint32 header length][header JSON][binary
sections]`. The header names each section's offset, length and dtype, and
carries the projection, frame metadata, street names, place list, shortlist and
`city`, the city-wide mean shade of every frame. Coordinates are `uint16`,
quantised to 0.5 m against an origin in the header. Shade is one byte per
segment per frame, **segment-major** within each date — that ordering alone
halves the gzipped size, because a segment's shade over consecutive half-hours
is smooth.

**Shade is split by date because unpacking it was most of a phone's boot.** It
is 29 MB of the 31 MB unpacked, and the page only ever reads one date of it, so
each of the 24 dates (`head.ndate`, `head.slots` = 32 frames each) is its own
gzip stream and boot inflates only the one it opens on. `D.shade` keeps its full
`[segment][frame]` shape and `frameAt()` — which every shade read goes through,
since today can be answered from any date — fills a date the first time it is
asked for. Measured with `measure_boot.mjs`:
boot 2.04 s → 0.91 s with the CPU slowed 4×, 0.49 s → 0.28 s on desktop. A date
then costs 155 ms / 56 ms the first time you switch to it. The price is size:
24 separate streams lose some of the segment-major compression, 2.76 → 3.56 MB
of gzip, and the file grew 5.4 → 6.4 MB. Twelve monthly streams would have cost
+20 % instead of +29 %, but they unpack twice as much at boot. Anything that
reads `D.shade` without going through `frameAt()` must call
`window.ombra.loadDate(d)` first — the smoke test does, and checks every date
lands in its own frames against `head.city`.

`window.ombra` exposes state and helpers (`st`, `head`, `data`, `setEnd`,
`recompute`, `nearestNode`, `labelForNode`, `screenXY`, `loadDate`, `BOOT`, `sunAt`,
`solarPos`, `cityTZ`, `dstWindow`, `me`) for debugging and for the
tests.

Drinking fountains ride along in two `u2` sections, `nax`/`nay` (named for Rome's
nasoni), quantised like everything else; `head.nnaso` is the count (14). They
carry no names: what you want from a fountain is that it is there.

The quantisation origin is the bbox corner less 900 m (outlines that cross the
edge keep their outside vertices), and values are clipped rather than wrapped.
The header also carries `proj`, `place` (name, clock), `labels` (map labels in
local metres), `netkm`, `bigpct`, `ntree`, `nrow`, `relief`, `hsrc` (where the
known heights came from) and `source`, so the methodology panel counts rather
than quotes. The boot and size figures above are Rome's; Detroit's file is
4.6 MB and `measure_boot.mjs` has not been re-run for it.

## Accuracy, measured

| | |
|---|---|
| Bare earth under the towers | ground under the 25 tallest tagged buildings reads −0.06 m against 50–100 m round them |
| Buildings in the box | 4,888 (by centroid); 4,608 carry a height, 25 a floor count, 255 estimated |
| Height sources | Esri Community Maps 3,325, USGS lidar 685, Microsoft ML 330, OSM tags 268 |
| Error of the estimate | IDW RMSE 4.18 m, MAE 2.49, bias +1.42 — leave-one-out on the 2,145 tagged buildings the size of the untagged |
| Shade's sensitivity to that error | 99.75 % of segment-frames unmoved, city mean −0.01 pp; the 0.25 % that move, move by a median 25 pp. ML heights are not in this test |
| Walking network | 42,334 links, ~867 km, 97.5 % one connected component, dead ends 6.7 % |
| Sunrise/sunset vs published | to the minute at both solstices, 1 min on 20 March |
| Today from the closest sun | 1.49 pp mean error (nearest date: 3.00) |

**Height error does not average out, it concentrates** — in Rome, perturbing the
estimated heights left 94.5 % of values bit-identical and moved the 5.5 % that
did by more than 10 pp; here the same probe touches 0.25 %, all of it hard.
Ray blocking is a threshold. Re-derive rather than copy:
`OMBRA_JITTER=<seed> python build_dsm.py && python shade.py`, then
`compare_frames.py` against a saved real `frames.npy`, then rebuild the real
grid. Call the scripts, not `make`, which would see nothing to rebuild.

Not modelled: awnings, scaffolding, the People Mover's elevated track, parked
trucks, cloud, humidity, or the heat off asphalt and parking lots. Tree canopy
comes from 3,452 mapped trees and is patchy.

## Possible next steps

- **A raw OSM fetch** (`fetch_osm.py` from a residential connection, then
  `SOURCE = "osm"`): church hours, street widths, wikidata for place ranking, and
  OSM height tags to score the Overture height sources against each other. Or
  keep Overture's heights and take only the tags from OSM.
- **The ML heights.** 330 buildings carry Microsoft's estimate as if it were a
  measurement. Scoring them needs a second height for the same buildings: OSM
  tags, or USGS 3DEP lidar point clouds directly.
- **Re-measure what is still Rome's:** `measure_via.mjs` (does "Route via one"
  earn its line with 14 fountains?), `measure_boot.mjs`, `measure_days.mjs`.
- **Wider coverage.** New Center, Woodbridge west of the Lodge, the east
  riverfront to Belle Isle are just outside the box. File size is ~4.6 MB for
  this one, far under the 16 MB artifact cap.

## Conventions

- Never hand-type coordinates. Everything resolves against the data — the
  shortlist and map labels in `places.py` are lists of *names*, matched at
  build time.
- Claims in the UI's methodology panel are measured, not asserted. If you change
  the model or the data, re-measure and update the numbers there.
- `tests/validate.py` guards the physics; `tests/smoke.mjs` guards the page.
  Run both before publishing.
