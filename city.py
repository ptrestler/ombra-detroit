"""The one place a city lives. Everything else asks this file.

Map area, projection origin, the sun's observer, the civil clock, and the
handful of names the build resolves against OpenStreetMap. Porting to another
city means editing this file and refetching data/, nothing else in the pipeline.
"""
import calendar

NAME   = "Ombra Detroit"          # the page title and the installed app's name
CITY   = "Detroit"                # how the page refers to the place
COUNTRY= "US"                     # the boundary the map is clipped to: area.py
SLUG   = "ombra-detroit"          # file names: dist/<SLUG>.html

# Where the map's data comes from: "osm" (fetch_osm.py, Overpass, data/osm/)
# or "overture" (fetch_overture.py, Overture Maps on S3, data/overture/). Both
# write the same files in the same shape; nothing downstream knows which.
SOURCE = "overture"

# The mapped area: downtown, Midtown, New Center, Corktown, Mexicantown and
# the riverfront. West to Clark Park (Mexicantown's centre is 83.0863 W in
# Overture's divisions), south to the river at the Ambassador Bridge, north
# past New Center (42.369 N) to Virginia Park.
S, W, N, E = 42.312, -83.106, 42.376, -83.030

# Projection origin and the sun's observer: the middle of the box. The shade
# model and the page both compute the sun from here, so they must agree.
LAT0, LON0 = round((S + N) / 2, 4), round((W + E) / 2, 4)

# --- civil time ------------------------------------------------------------
# US rule since 2007: summer time from the second Sunday of March to the first
# Sunday of November. Eastern: -5 standard, -4 summer. The frames start at
# 06:00, after the 02:00 switch, so a whole date is on one side of it.
TZ_NAME = "America/Detroit"
TZ_STD, TZ_DST = -5, -4
DST_RULE = "us"

def _nth_sunday(y, m, n):
    d = 1 + (6 - calendar.weekday(y, m, 1)) % 7
    return d + 7 * (n - 1)

def dst_window(y):
    """((month, day) summer time starts, (month, day) it ends)."""
    return (3, _nth_sunday(y, 3, 2)), (11, _nth_sunday(y, 11, 1))

def tz_for(y, mo, day):
    start, end = dst_window(y)
    return TZ_DST if start <= (mo, day) < end else TZ_STD

# Drinking fountains on the map and on walks ("Route via one"). Rome's nasoni
# run all day on every other corner; Detroit's handful of mapped ones are not
# something to plan a walk round, so the payload carries none and the page
# shows no fountain, no water line and no water stop.
FOUNTAINS = False

# --- what the page is told ---------------------------------------------------
UNITS = "mi"                      # the default until someone chooses: "mi" or "km"
DESCRIPTION = ("Ray-traced shade map and shade-aware walking routes for downtown "
               "Detroit, Midtown, New Center, Corktown, Mexicantown and the riverfront.")
PAGES_URL = "ptrestler.github.io/ombra-detroit"

def fill(body):
    """The template's city tokens, filled. Both builders call this, so the
    standalone and the artifact cannot name different places."""
    for k, v in (("__APPNAME__", NAME), ("__CITY__", CITY), ("__TZNAME__", TZ_NAME),
                 ("__UNITS__", UNITS), ("__PAGESURL__", PAGES_URL)):
        body = body.replace(k, v)
    return body
