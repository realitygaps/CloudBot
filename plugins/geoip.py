import socket
import time
import requests
import gzip
import asyncio
import shutil
import logging
import os.path
import geoip2.database
import geoip2.errors

from cloudbot import hook

logger = logging.getLogger("cloudbot")

DB_URL = "http://geolite.maxmind.com/download/geoip/database/GeoLite2-City.mmdb.gz"
PATH = "./data/GeoLite2-City.mmdb"

geoip_reader = None


def fetch_db():
    r = requests.get(DB_URL, stream=True)
    if r.status_code == 200:
        with gzip.open(r.raw, 'rb') as infile:
            with open(PATH, 'wb') as outfile:
                shutil.copyfileobj(infile, outfile)


def update_db():
    """
    Updates the DB.
    """
    if os.path.isfile(PATH):
        # check if file is over 2 weeks old
        if time.time() - os.path.getmtime(PATH) > (14 * 24 * 60 * 60):
            # geoip is outdated, re-download
            fetch_db()
            return geoip2.database.Reader(PATH)
        else:
            try:
                return geoip2.database.Reader(PATH)
            except:
                # issue loading, geo
                fetch_db()
                return geoip2.database.Reader(PATH)
    else:
        # no geoip file
        fetch_db()
        return geoip2.database.Reader(PATH)


def check_db(loop):
    """
    runs update_db in an executor thread and sets geoip_reader to the result
    if this is run while update_db is already executing bad things will happen
    """
    global geoip_reader
    if not geoip_reader:
        logger.info("Loading GeoIP database")
        db = yield from loop.run_in_executor(None, update_db, geoip_reader)
        logger.info("Loaded GeoIP database")
        if db:
            geoip_reader = db


@asyncio.coroutine
@hook.onload
def load_geoip(loop):
    asyncio.async(check_db(loop), loop=loop)


@asyncio.coroutine
@hook.command
def geoip(text, reply, loop):
    global geoip_reader

    if not geoip_reader:
        return "GeoIP database is still loading, please wait a minute"

    try:
        ip = yield from loop.run_in_executor(None, socket.gethostbyname, text)
    except socket.gaierror:
        return "Invalid input."

    try:
        location_data = yield from loop.run_in_executor(None, geoip_reader.city, ip)
    except geoip2.errors.AddressNotFoundError:
        return "Sorry, I can't locate that in my database."

    data = {
        "cc": location_data.country.iso_code or "N/A",
        "country": location_data.country.name or "Unknown",
        "city": location_data.city.name or "Unknown",
        "region": ", " + location_data.subdivisions.most_specific.name or ""
    }

    reply("\x02Country:\x02 {country} ({cc}), \x02City:\x02 {city}{region}".format(**data))
