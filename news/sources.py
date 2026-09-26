"""GovEase - registry of official government feeds.

THIS IS THE EXTENSION POINT. To add a source, append one dict below.
The collector needs no changes.

IMPORTANT - every URL in SOURCES was fetched and confirmed to return a
parseable feed before being added. Never add a URL that has not been
verified this way: an invented or stale endpoint produces either silent
failure or, worse, an official-looking link that goes nowhere.

Verification run: 2026-09-13. 16 candidates probed, 5 kept.

Dropped, and why:
  india.gov.in, ISRO, DST, EPFO, DGFT, CBIC,
  Digital India, indiabudget, PRS, NIC      - HTTP 404, no feed at that path
  MeitY, Ministry of Education, UGC, MEA    - HTTP 200 but HTML, not a feed
  RBI /Scripts/Rss.aspx                     - HTML wrapper; the working RBI
                                              feed is pressreleases_rss.xml
  DD News, MoHFW                            - connection reset
  newsonair.gov.in                          - read timeout
  PM India (pmindia.gov.in/en/feed/)        - parses, but contains a single
                                              'test post' entry from 2024.
                                              Nothing publishable.
  Income Tax (incometax.gov.in .../rss.xml) - parses, but titles are internal
                                              asset names such as
                                              'e_campaigns_email_09_03.2',
                                              not citizen-readable updates.
  PIB (pib.gov.in RssMain.aspx)             - the one working endpoint
                                              (ModId=6&Lang=1&Regid=3) serves
                                              HINDI content regardless of the
                                              Lang parameter; Regid 0/1/2/4/5
                                              and RssEng.aspx all return empty
                                              feeds. This interface is English,
                                              so Hindi headlines would render
                                              as unreadable noise beside the
                                              other sources. Worth re-adding if
                                              an English PIB feed is found -
                                              it is otherwise the single best
                                              government source available.

Re-check the dropped ones occasionally; several are plausible future sources
if their feeds are fixed.

Fields:
  name              display name, also the primary key in the sources table
  url               verified feed URL
  department        ministry / body the update belongs to
  default_category  used when keyword matching finds nothing specific
  state_level       'Central' or 'State'
"""

SOURCES = [
    {
        "name": "Reserve Bank of India",
        "url": "https://rbi.org.in/pressreleases_rss.xml",
        "department": "Reserve Bank of India",
        "default_category": "Policies",
        "state_level": "Central",
    },
    {
        "name": "MyGov",
        "url": "https://www.mygov.in/rss.xml",
        "department": "MyGov, Government of India",
        "default_category": "Citizen Services",
        "state_level": "Central",
    },
    {
        "name": "SEBI",
        "url": "https://www.sebi.gov.in/sebirss.xml",
        "department": "Securities and Exchange Board of India",
        "default_category": "Notifications",
        "state_level": "Central",
    },
    {
        "name": "TRAI",
        "url": "https://www.trai.gov.in/rss.xml",
        "department": "Telecom Regulatory Authority of India",
        "default_category": "Citizen Services",
        "state_level": "Central",
    },
    {
        "name": "NITI Aayog",
        "url": "https://www.niti.gov.in/rss.xml",
        "department": "NITI Aayog",
        "default_category": "Policies",
        "state_level": "Central",
    },
]


def get_sources():
    return list(SOURCES)


def get_source(name):
    for source in SOURCES:
        if source["name"] == name:
            return source
    return None
