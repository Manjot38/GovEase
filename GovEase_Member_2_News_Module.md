# GovEase --- Government News & Updates Module

## Member 2 Development Plan + Frontend Integration Specification

## 1. Module Purpose

The **Government News & Updates** module is a dedicated section of
GovEase that presents important government updates in a simple,
organized, and trustworthy newspaper-style interface.

It will cover: - New government schemes - Government announcements -
Policy decisions - Notifications - Eligibility changes - Important
deadlines - Public notices - Citizen-related government updates

The module should feel like a **modern government information portal**,
not a normal news website.

The main goal is:

**Official Government Source → Collect/Process Update → Categorize &
Store → Verify → Display in GovEase → Open Original Source**

------------------------------------------------------------------------

# 2. Overall GovEase Website Flow

``` text
                         GOVeASE
                            |
             +--------------+--------------+
             |              |              |
        AI Assistant     News & Updates   File/Form Tool
             |              |              |
       Member 1 work     Member 2 work    Member 3 work
                            |
                  Official Government Sources
                            |
                  Collect / Process Updates
                            |
                    Store Structured Data
                            |
                    Verify Source + Date
                            |
                    Categorize News
                            |
                  Government News Feed
                            |
             Search / Filter / Categories
                            |
                 Full Update / Source Link
```

The frontend should be built in a way that **Member 1 and Member 3 can
later connect their backend/API without redesigning the complete
website**.

------------------------------------------------------------------------

# 3. News Module User Flow

## Step 1 --- Open GovEase

User lands on the GovEase homepage.

The website should immediately communicate:

> **GovEase --- Simplifying Government Services**

Main navigation:

-   Home
-   AI Assistant
-   Government Updates
-   Schemes & Services
-   Documents & Forms
-   About

The last two sections can initially be placeholders if their backend is
not ready.

------------------------------------------------------------------------

## Step 2 --- Government Updates

User opens:

**Government Updates**

This page should look like a **digital government newspaper**.

Top section:

### Government Updates

**Important announcements, schemes, policies and notifications from
verified government sources.**

Show: - Last updated time - Search - Category filters - State/Central
filter if data supports it

------------------------------------------------------------------------

# 4. Newspaper-Style Layout

The page should have a strong newspaper/newsroom feeling while still
looking official.

## Header Area

``` text
GOVeASE
Government Updates

Latest verified government announcements
[ Search government updates... ]

[ All ] [ Schemes ] [ Announcements ] [ Policies ]
[ Notifications ] [ Citizen Services ]
```

------------------------------------------------------------------------

# 5. Main News Layout

Use a newspaper-inspired hierarchy instead of showing identical cards
everywhere.

## Featured Update

At the top:

``` text
FEATURED UPDATE

[Large headline]

Short 2–3 line summary

Department / Ministry
Date
Source: Official Government Website

[Read Full Update]
```

The featured item should visually stand out.

------------------------------------------------------------------------

## Latest Updates

Below the featured section:

``` text
LATEST GOVERNMENT UPDATES

------------------------------------------------
Headline
Department • Date
Short summary
[Read Update]
------------------------------------------------

Headline
Department • Date
Short summary
[Read Update]
------------------------------------------------
```

Use a mixture of: - Large featured story - Medium news cards - Compact
update list

This will make the page look more like a **heavy project / government
portal** rather than a simple CRUD dashboard.

------------------------------------------------------------------------

# 6. Category System

Every update should have a category.

Recommended categories:

-   Schemes
-   Announcements
-   Policies
-   Notifications
-   Citizen Services
-   Eligibility Updates
-   Deadlines
-   Education
-   Employment
-   Agriculture
-   Health
-   Other

Do not create unnecessary categories if there is insufficient data.

------------------------------------------------------------------------

# 7. Important News Information

Each news item should store/display:

``` text
Title
Short Summary
Category
Department / Ministry
Published Date
Last Checked Date
Source Name
Original Source Link
State / Central
Importance
```

Optional:

``` text
Deadline
Eligibility
Location
Tags
```

The **original government source link is essential**.

GovEase should not present itself as the original authority. It should
clearly direct users to the official source.

------------------------------------------------------------------------

# 8. Update Detail Page

When the user clicks a news item:

``` text
Government Updates
        ↓
Update Detail
```

Show:

### Title

### Department / Ministry

### Published Date

### Last Verified

### Category

### Summary

A clear citizen-friendly explanation of the update.

### Important Points

-   What has changed?
-   Who may be affected?
-   What is the important date?
-   What should citizens do?

### Official Source

``` text
Source: [Government Department]
[View Official Notification]
```

The official source should open in a new tab.

------------------------------------------------------------------------

# 9. Verification / Trust Design

Trust should be a major visual element.

Use labels such as:

**✓ Verified Government Source**

and:

**Last checked: 12 Sep 2026**

Do not claim that an update is officially verified unless the backend
actually checks the source.

The frontend should support fields such as:

``` text
source_name
source_url
published_date
last_checked
department
```

This will later connect naturally to Member 2's backend.

------------------------------------------------------------------------

# 10. Backend/Data Flow for Member 2

Recommended pipeline:

``` text
Official Government Websites / APIs / RSS
                  ↓
          Data Collection
                  ↓
         Extract Relevant Content
                  ↓
          Clean & Normalize Text
                  ↓
          Remove Duplicate Updates
                  ↓
             Categorize
                  ↓
       Extract Important Metadata
                  ↓
          Store in Database
                  ↓
        Verification Metadata
                  ↓
            GovEase API
                  ↓
              Frontend
```

The system should prioritize **official government sources**.

Examples of source types:

-   Ministry websites
-   Department websites
-   Government notification pages
-   Official portals
-   Official RSS/API where available

Do not make random news websites the primary source.

------------------------------------------------------------------------

# 11. Suggested Database Structure

A simple news table/document can contain:

``` text
id
title
summary
category
department
published_date
last_checked
source_name
source_url
state_level
importance
tags
content
```

Optional:

``` text
deadline
location
image_url
```

Keep the structure simple so other members can easily integrate with it.

------------------------------------------------------------------------

# 12. API Structure

Build the frontend so it can consume APIs later.

Suggested endpoints:

``` text
GET /api/news
GET /api/news/<id>
GET /api/news?category=schemes
GET /api/news?search=...
GET /api/news?department=...
GET /api/news?state=...
```

Possible response:

``` json
{
  "id": 1,
  "title": "Example Government Update",
  "summary": "Short citizen-friendly summary.",
  "category": "Schemes",
  "department": "Example Ministry",
  "published_date": "2026-09-12",
  "last_checked": "2026-09-12",
  "source_name": "Official Government Website",
  "source_url": "official-source-link"
}
```

The exact backend technology can be decided later.

------------------------------------------------------------------------

# 13. Frontend Architecture

## Main Pages

``` text
/
├── Home
├── AI Assistant
├── Government Updates
│   ├── All Updates
│   └── Update Details
├── Documents & Forms
└── About
```

The frontend should be modular.

Do not hard-code the complete news content into HTML.

Initially, mock JSON data can be used.

Later:

``` text
Mock JSON
   ↓
Backend API
   ↓
Database / Collector
```

This allows easy integration.

------------------------------------------------------------------------

# 14. Homepage News Section

The homepage should also contain a small Government Updates section.

Example:

``` text
--------------------------------------------------
LATEST GOVERNMENT UPDATES

01  New Government Scheme Announced
    Ministry / Department • 12 Sep 2026

02  Important Notification Released
    Department • 11 Sep 2026

03  Eligibility Rules Updated
    Ministry • 10 Sep 2026

                 [View All Updates]
--------------------------------------------------
```

This gives the project a more complete government-portal feel.

------------------------------------------------------------------------

# 15. Government Website Visual Direction

The design should feel inspired by **official Indian government
portals**, but should not copy any specific website.

## Visual Characteristics

-   Clean and formal
-   Strong information hierarchy
-   White/light background
-   Deep official-looking accent color
-   Dark text
-   Thin borders
-   Structured sections
-   Government-style typography
-   Accessible contrast
-   Minimal unnecessary gradients
-   Limited decorative animation

Avoid: - Gaming-style UI - Excessive glassmorphism - Neon colors - Huge
animations - Social-media-style layouts - Overly rounded cards
everywhere - generate too many files(conclude in 2-3 files only)

The website should look like:

**Government Portal + Modern Digital Service + Newspaper**

------------------------------------------------------------------------

# 16. Heavy Project Feel

The project should feel substantial through **functionality**, not just
visual effects.

Include:

### Trust Layer

-   Verified source
-   Department
-   Published date
-   Last checked

### Discovery Layer

-   Search
-   Categories
-   Filters
-   Latest/Important sorting

### Information Layer

-   Featured update
-   Latest updates
-   Detailed update page
-   Important points

### Data Layer

-   Government source collection
-   Cleaning
-   Deduplication
-   Categorization
-   Database
-   API

This will make the module look like a real system rather than a static
news page.

------------------------------------------------------------------------

# 17. Frontend Integration With Other Members

The frontend should reserve clear integration points.

## AI Assistant

Member 1 can later connect:

``` text
AI Assistant Page
       ↓
RAG API
       ↓
Verified Government Knowledge Base
```

The assistant should have its own interface and should not interfere
with the news API.

------------------------------------------------------------------------

## Smart Document/Form Tool

Member 3 can later connect:

``` text
Documents & Forms
       ↓
Upload
       ↓
Python Processing API
       ↓
Compression / Resize / Conversion
       ↓
Download
```

The frontend should only need to send the file to the backend API.

------------------------------------------------------------------------

# 18. Recommended Technology Stack

## Frontend

Use a simple stack:

``` text
HTML
CSS
JavaScript
```

or the existing frontend framework if the team has already selected one.

Claude can help generate and refine the UI.

## Backend

Member 2:

``` text
Python
Flask / FastAPI
```

## Data

Possible:

``` text
SQLite
PostgreSQL
MongoDB
```

For the initial prototype, SQLite is sufficient.

## Data Collection

Depending on source availability and permission:

``` text
Requests
BeautifulSoup
RSS/API
```

Do not depend on aggressive scraping of government websites.

------------------------------------------------------------------------

# 19. Development Order

Follow this order to avoid wasting time.

## Phase 1 --- Project UI

Build:

-   Navbar
-   Homepage
-   Government Updates page
-   Update detail page
-   Footer
-   Responsive layout

Use temporary JSON data.

------------------------------------------------------------------------

## Phase 2 --- News UI

Add:

-   Featured update
-   Latest updates
-   Categories
-   Search
-   Filters
-   Update details
-   Verified source badge
-   Last checked information

------------------------------------------------------------------------

## Phase 3 --- Backend

Create:

``` text
News database
       ↓
News API
       ↓
Frontend
```

Replace mock JSON with API data.

------------------------------------------------------------------------

## Phase 4 --- Data Collection

Build:

``` text
Official sources
       ↓
Collector
       ↓
Cleaner
       ↓
Duplicate removal
       ↓
Category assignment
       ↓
Database
```

Start with a limited number of reliable sources instead of trying to
cover every government website.

------------------------------------------------------------------------

## Phase 5 --- Integration

After your part is stable:

``` text
Member 1 → AI Assistant API
Member 2 → News API
Member 3 → Document Processing API
```

Connect all three to the same GovEase frontend.

------------------------------------------------------------------------

# 20. Final User Journey

A citizen opens GovEase.

``` text
HOME
  ↓
See latest government updates
  ↓
Open Government Updates
  ↓
Search/filter required information
  ↓
Open update
  ↓
Read simplified summary
  ↓
See department + date + verification
  ↓
Open official government source
```

At the same time:

``` text
Need government information?
        ↓
AI Assistant

Need latest announcements?
        ↓
Government Updates

Need application-ready photo/document?
        ↓
Smart Form & Document Preparation
```

This gives GovEase a clear identity:

> **One platform for understanding government information, staying
> updated with government announcements, and preparing files for online
> applications.**

------------------------------------------------------------------------

# 21. Important Scope Control

Do not try to build a complete national government news crawler
immediately.

For the major-project prototype:

-   Start with selected reliable government sources.
-   Demonstrate multiple categories.
-   Store source and verification metadata.
-   Show the complete collection → processing → database → API →
    frontend pipeline.
-   Keep the architecture expandable.

A working system with **10--20 properly processed sources/updates** is
better than a large unreliable scraping system.

------------------------------------------------------------------------

# 22. Member 2 Deliverables

By the end of your part, you should have:

### Frontend

-   [ ] GovEase main layout
-   [ ] Government Updates page
-   [ ] Featured news section
-   [ ] Latest updates
-   [ ] Category filters
-   [ ] Search
-   [ ] Update detail page
-   [ ] Source/verification information
-   [ ] Responsive design

### Backend

-   [ ] News database
-   [ ] News API
-   [ ] Source metadata
-   [ ] Category system
-   [ ] Search/filter API
-   [ ] Duplicate handling
-   [ ] Update timestamps

### Data Pipeline

-   [ ] Selected official sources
-   [ ] Data collection method
-   [ ] Cleaning
-   [ ] Categorization
-   [ ] Source verification metadata

### Integration

-   [ ] API documentation
-   [ ] Clear API endpoints
-   [ ] Mock data fallback
-   [ ] Frontend ready for Member 1 and Member 3 APIs

------------------------------------------------------------------------

# 23. Suggested Final Project Structure

``` text
GovEase/
│
├── frontend/
│   ├── index.html
│   ├── news.html
│   ├── news-detail.html
│   ├── styles.css
│   └── script.js
│
├── backend/
│   ├── app.py
│   ├── routes/
│   ├── models/
│   └── database/
│
├── news/
│   ├── collector.py
│   ├── cleaner.py
│   ├── categorizer.py
│   └── data/
│
├── api/
│   └── news_api.md
│
└── README.md
```

The exact structure can be simplified depending on the team's final
stack.

------------------------------------------------------------------------

# 24. Key Principle

**Do not make the Government News module another chatbot.**

Its primary workflow is:

> **Collect → Process → Verify → Organize → Display → Link to Official
> Source**

That makes it a distinct GovEase module and gives Member 2 a substantial
technical contribution.

------------------------------------------------------------------------

# 25. Performance Requirements

The Government Updates module must stay fast and lightweight. These
requirements are binding on the implementation.

## Response Behaviour

-   Government Updates must remain lightweight and fast.
-   `/api/news` must return existing SQLite data **immediately**.
-   If news data is older than the configured freshness threshold,
    trigger the source refresh **in the background**.
-   **Never block the user's page** while RSS/API sources are being
    checked.
-   Use **one global freshness check**, not a separate timer/check for
    every source or every request.

## Source Collection

-   Start with only **5--10 verified** official RSS/API sources.
-   Each source request must have a **short timeout** and must **fail
    independently**.
-   Collect only the **latest limited number of items per source**; do
    not build a large historical archive.
-   **Deduplicate before storing** records.
-   Do **not** run a 24/7 crawler.
-   The background scheduler must be **optional and OFF by default**.

## Frontend

-   Do **not** continuously poll the frontend.
-   Keep images lightweight and **lazy-load** them.
-   Do **not** add heavy frontend frameworks, animation libraries, chart
    libraries, or unnecessary dependencies.

## Resilience and Honesty

-   The page must remain usable even if **all external government
    sources are temporarily unavailable**, by serving existing database
    data.
-   **"Last checked"** must show the freshness of the latest
    source-check cycle.
-   A 5-minute interval is a **freshness target / check interval, not a
    guarantee** that every government announcement will appear within
    exactly 5 minutes.
