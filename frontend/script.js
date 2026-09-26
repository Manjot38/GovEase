/* ==========================================================================
   GovEase - shared frontend script

   ONE global, GovEase, split into namespaces so the three members never
   collide:

     GovEase.config     shared settings
     GovEase.api        the ONLY place fetch() is called   (Member 2)
     GovEase.news       Government Updates rendering       (Member 2)
     GovEase.assistant  RESERVED for Member 1 (RAG assistant)
     GovEase.docs       RESERVED for Member 3 (document/form tool)

   Rules this file follows, from spec section 25:
     - No polling. Data is fetched on page load and on user action only.
     - No third-party library of any kind.
     - Images are lazy-loaded.
     - If the API is unreachable, fall back to the committed cached snapshot
       of real government updates so the page still works.
   ========================================================================== */

window.GovEase = window.GovEase || {};

(function (G) {
  'use strict';

  /* --- Config ------------------------------------------------------------ */

  G.config = {
    // Same-origin when served by Flask; explicit host when the frontend is
    // served separately (e.g. python -m http.server on another port).
    API_BASE:
      window.location.port === '5000' || window.location.protocol === 'file:'
        ? '/api'
        : 'http://localhost:5000/api',
    FALLBACK: '../news/data/seed_news.json',
    PAGE_SIZE: 24
  };

  // State shared between the api layer and the renderers.
  G.state = { offline: false, lastChecked: null, hasCached: false, snapshotDate: null };

  /* --- Utilities --------------------------------------------------------- */

  var U = {
    /* Feed content is third-party. It is never trusted as HTML. */
    escape: function (value) {
      if (value === null || value === undefined) return '';
      return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    },

    /* Only http(s) links are ever rendered as clickable. */
    safeUrl: function (url) {
      if (!url) return null;
      return /^https?:\/\//i.test(String(url).trim()) ? String(url).trim() : null;
    },

    formatDate: function (value) {
      if (!value) return 'Date not stated';
      var d = new Date(value);
      if (isNaN(d.getTime())) return String(value);
      return d.toLocaleDateString('en-IN', {
        day: '2-digit', month: 'short', year: 'numeric'
      });
    },

    /* "Last checked" is deliberately phrased as an observation, never a
       promise about how current the data is. */
    relativeTime: function (value) {
      if (!value) return 'not checked yet';
      var then = new Date(value);
      if (isNaN(then.getTime())) return String(value);
      var mins = Math.floor((Date.now() - then.getTime()) / 60000);
      if (mins < 1) return 'just now';
      if (mins === 1) return '1 minute ago';
      if (mins < 60) return mins + ' minutes ago';
      var hrs = Math.floor(mins / 60);
      if (hrs === 1) return '1 hour ago';
      if (hrs < 24) return hrs + ' hours ago';
      var days = Math.floor(hrs / 24);
      return days === 1 ? '1 day ago' : days + ' days ago';
    },

    debounce: function (fn, wait) {
      var timer = null;
      return function () {
        var ctx = this, args = arguments;
        clearTimeout(timer);
        timer = setTimeout(function () { fn.apply(ctx, args); }, wait);
      };
    },

    qs: function (name) {
      return new URLSearchParams(window.location.search).get(name);
    },

    /* Mirrors is_official_source() in backend/models/news.py. Needed because
       the offline fallback reads the snapshot file directly and so has to
       work out the trust state itself. An exact-match set plus a dotted
       suffix set, so a lookalike host like "notgov.in" cannot pass. */
    isOfficialHost: function (url) {
      var match = /^https?:\/\/([^/:?#]+)/i.exec(String(url || '').trim());
      if (!match) return false;
      var host = match[1].toLowerCase().replace(/\.$/, '');
      if (host === 'gov.in' || host === 'nic.in') return true;
      if (/\.gov\.in$/.test(host) || /\.nic\.in$/.test(host)) return true;
      return ['rbi.org.in', 'mygov.in'].some(function (extra) {
        return host === extra || host.endsWith('.' + extra);
      });
    }
  };

  G.util = U;

  /* --- API layer --------------------------------------------------------- */

  var seedCache = null;

  function loadSeed() {
    if (seedCache) return Promise.resolve(seedCache);
    return fetch(G.config.FALLBACK)
      .then(function (r) {
        if (!r.ok) throw new Error('seed unavailable');
        return r.json();
      })
      .then(function (items) {
        // Snapshot rows are real records previously collected from the
        // official feeds, so they keep their source URL and earn the same
        // trust state the API would have given them.
        var newest = null;
        seedCache = items.map(function (item, index) {
          if (item.published_date && (!newest || item.published_date > newest)) {
            newest = item.published_date;
          }
          return Object.assign({}, item, {
            id: 'cached-' + index,
            data_origin: 'cached',
            source_url: item.source_url || null,
            is_official_source: U.isOfficialHost(item.source_url),
            detected_at: null,
            last_checked: null
          });
        });
        G.state.snapshotDate = newest;
        return seedCache;
      });
  }

  /* Client-side equivalent of the API's filtering, used only in fallback
     mode so the page behaves the same way with the backend down. */
  function filterSeed(items, params) {
    var out = items.slice();
    if (params.category && params.category !== 'All') {
      out = out.filter(function (i) { return i.category === params.category; });
    }
    if (params.state && params.state !== 'All') {
      out = out.filter(function (i) { return i.state_level === params.state; });
    }
    if (params.search) {
      var q = params.search.toLowerCase();
      out = out.filter(function (i) {
        var tags = Array.isArray(i.tags) ? i.tags.join(' ') : (i.tags || '');
        return (i.title || '').toLowerCase().indexOf(q) !== -1 ||
               (i.summary || '').toLowerCase().indexOf(q) !== -1 ||
               tags.toLowerCase().indexOf(q) !== -1;
      });
    }
    out.sort(function (a, b) {
      return String(b.published_date || '').localeCompare(String(a.published_date || ''));
    });
    return out;
  }

  G.api = {
    getNews: function (params) {
      params = params || {};
      var query = new URLSearchParams();
      Object.keys(params).forEach(function (key) {
        var value = params[key];
        if (value !== null && value !== undefined && value !== '' && value !== 'All') {
          query.set(key, value);
        }
      });

      return fetch(G.config.API_BASE + '/news?' + query.toString())
        .then(function (r) {
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.json();
        })
        .then(function (data) {
          G.state.offline = false;
          G.state.lastChecked = data.last_checked;
          return data;
        })
        .catch(function () {
          // API unreachable: serve the committed cached snapshot instead of
          // showing the user an empty page.
          G.state.offline = true;
          return loadSeed().then(function (items) {
            var filtered = filterSeed(items, params);
            var limit = parseInt(params.limit, 10) || G.config.PAGE_SIZE;
            return {
              count: Math.min(filtered.length, limit),
              total: filtered.length,
              last_checked: null,
              results: filtered.slice(0, limit)
            };
          });
        });
    },

    getNewsById: function (id) {
      if (String(id).indexOf('cached-') === 0) {
        return loadSeed().then(function (items) {
          return items.filter(function (i) { return i.id === id; })[0] || null;
        });
      }
      return fetch(G.config.API_BASE + '/news/' + encodeURIComponent(id))
        .then(function (r) {
          if (r.status === 404) return null;
          if (!r.ok) throw new Error('HTTP ' + r.status);
          G.state.offline = false;
          return r.json();
        })
        .catch(function () {
          G.state.offline = true;
          return loadSeed().then(function (items) {
            return items.filter(function (i) { return String(i.id) === String(id); })[0] || null;
          });
        });
    },

    getMeta: function () {
      return fetch(G.config.API_BASE + '/meta')
        .then(function (r) {
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.json();
        })
        .then(function (data) {
          G.state.offline = false;
          G.state.lastChecked = data.last_checked;
          G.state.hasCached = !!data.has_cached_data;
          return data;
        })
        .catch(function () {
          G.state.offline = true;
          return loadSeed().then(function (items) {
            var counts = {};
            items.forEach(function (i) {
              counts[i.category] = (counts[i.category] || 0) + 1;
            });
            G.state.hasCached = true;
            return {
              last_checked: null,
              categories: Object.keys(counts).map(function (c) {
                return { category: c, count: counts[c] };
              }).sort(function (a, b) { return b.count - a.count; }),
              state_levels: ['Central', 'State'],
              has_cached_data: true,
              offline: true
            };
          });
        });
    },

    refresh: function () {
      return fetch(G.config.API_BASE + '/refresh', { method: 'POST' })
        .then(function (r) { return r.json(); })
        .catch(function () { return { status: 'unreachable' }; });
    }
  };

  /* --- Shared rendering pieces ------------------------------------------- */

  var CHECK_SVG =
    '<svg viewBox="0 0 16 16" aria-hidden="true" fill="currentColor">' +
    '<path d="M6.2 11.6 2.9 8.3l1.1-1.1 2.2 2.2 5.8-5.8 1.1 1.1z"/></svg>';

  /* The three honest trust states (spec section 9). A verified badge is only
     ever shown for a link on a confirmed government host. */
  G.renderTrust = function (item) {
    var cached = item.data_origin === 'cached';
    if (item.is_official_source) {
      // A real government source either way; 'cached' only means the copy
      // may be out of date, which the page banner states.
      return '<span class="badge badge-verified">' + CHECK_SVG +
             'Verified Government Source' +
             (cached ? ' (cached)' : '') + '</span>';
    }
    return '<span class="badge badge-source">Source: ' +
           U.escape(item.source_name || 'Not stated') +
           (cached ? ' (cached)' : '') + '</span>';
  };

  G.renderSourceLink = function (item, label) {
    var url = U.safeUrl(item.source_url);
    if (!url) return '';
    return '<a class="btn btn-secondary" href="' + U.escape(url) +
           '" target="_blank" rel="noopener noreferrer">' +
           (label || 'View Official Notification') + '</a>';
  };

  /* Emits data-cat so CSS can pick the category's accent colour. Purely
     presentational - the value is the same category string the API sends. */
  G.catAttr = function (item) {
    return ' data-cat="' + U.escape(item.category || 'Other') + '"';
  };

  G.detailHref = function (item) {
    return 'news-detail.html?id=' + encodeURIComponent(item.id);
  };

  /* Images are optional in the data and always lazy, with dimensions set so
     they cannot shift the layout as they arrive. */
  G.renderThumb = function (item) {
    var url = U.safeUrl(item.image_url);
    if (!url) return '';
    return '<img class="card-thumb" src="' + U.escape(url) + '" alt="" ' +
           'loading="lazy" decoding="async" width="640" height="300">';
  };

  var INFO_SVG =
    '<svg viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" ' +
    'stroke-width="1.5"><circle cx="8" cy="8" r="6.3"/><path d="M8 7.3v4M8 4.9v.9"/></svg>';

  G.renderBanners = function () {
    var html = '';
    if (G.state.offline) {
      html += '<div class="banner banner-offline">' + INFO_SVG +
              '<span><strong>Offline.</strong> ' +
              'The GovEase API is unreachable, so this page is showing the ' +
              'bundled cached snapshot. Start the backend to see live ' +
              'government updates.</span></div>';
    }
    if (G.state.hasCached) {
      var asOf = G.state.snapshotDate
        ? ' The newest item in it is dated ' +
          U.escape(U.formatDate(G.state.snapshotDate)) + '.'
        : '';
      html += '<div class="banner banner-cached">' + INFO_SVG +
              '<span><strong>Cached snapshot.</strong> ' +
              'Items marked <em>cached</em> are real updates collected earlier ' +
              'from the official feeds, so they may be out of date.' + asOf +
              ' Each one still links to its original government notification.' +
              '</span></div>';
    }
    return html;
  };

  /* --- Navigation -------------------------------------------------------- */

  G.initNav = function () {
    var toggle = document.querySelector('.nav-toggle');
    var nav = document.getElementById('mainnav');
    if (!toggle || !nav) return;

    function setOpen(open) {
      nav.classList.toggle('is-open', open);
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    }

    toggle.addEventListener('click', function () {
      setOpen(!nav.classList.contains('is-open'));
    });

    // Choosing a destination should close the menu, including same-page
    // anchors where no navigation happens.
    nav.addEventListener('click', function (event) {
      if (event.target.closest('a')) setOpen(false);
    });

    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && nav.classList.contains('is-open')) {
        setOpen(false);
        toggle.focus();
      }
    });
  };

  document.addEventListener('DOMContentLoaded', function () {
    G.initNav();
    var year = document.getElementById('year');
    if (year) year.textContent = new Date().getFullYear();
  });

  /* --- Member 1 / Member 3 reserved slots --------------------------------
     Leave these namespaces free. Attach your own code as:
         GovEase.assistant = { init: function () { ... } };
         GovEase.docs      = { init: function () { ... } };
     and mount into #assistant-mount / #documents-mount on index.html.
     Do not add your fetch() calls to GovEase.api - keep your own client so
     the news module and yours can fail independently.
     ---------------------------------------------------------------------- */

})(window.GovEase);


/* ==========================================================================
   GovEase.news - Government Updates rendering (Member 2)
   ========================================================================== */

(function (G) {
  'use strict';

  var U = G.util;

  // Current filter state. Mirrored into the URL so views are shareable and
  // the back button works.
  var filters = { category: 'All', state: 'All', search: '' };

  function readFiltersFromUrl() {
    filters.category = U.qs('category') || 'All';
    filters.state = U.qs('state') || 'All';
    filters.search = U.qs('search') || '';
  }

  function writeFiltersToUrl(replace) {
    var query = new URLSearchParams();
    if (filters.category !== 'All') query.set('category', filters.category);
    if (filters.state !== 'All') query.set('state', filters.state);
    if (filters.search) query.set('search', filters.search);
    var url = window.location.pathname + (query.toString() ? '?' + query : '');
    if (replace) {
      window.history.replaceState(filters, '', url);
    } else {
      window.history.pushState(filters, '', url);
    }
  }

  /* --- Item templates ---------------------------------------------------- */

  /* Several feeds (SEBI, and PIB-style title-only items) repeat the title as
     the summary. Showing it twice looks broken, so suppress the duplicate
     rather than padding the card with filler. */
  function summaryOf(item) {
    var summary = (item.summary || '').trim();
    var title = (item.title || '').trim();
    if (!summary) return '';
    var a = summary.replace(/[\s.]+$/, '').toLowerCase();
    var b = title.replace(/[\s.]+$/, '').toLowerCase();
    return a === b ? '' : summary;
  }

  function metaLine(item) {
    return '<span class="item-meta">' +
      '<span class="dept">' + U.escape(item.department || item.source_name || '') + '</span>' +
      '<span class="sep" aria-hidden="true">&bull;</span>' +
      '<time datetime="' + U.escape(item.published_date || '') + '">' +
        U.escape(U.formatDate(item.published_date)) +
      '</time>' +
      '</span>';
  }

  function featuredHtml(item) {
    return '' +
      '<article class="featured"' + G.catAttr(item) + '>' +
        '<div>' +
          '<span class="featured-kicker">Featured Update</span>' +
          '<span class="cat-tag">' + U.escape(item.category || 'Other') + '</span>' +
          '<h3><a href="' + G.detailHref(item) + '">' + U.escape(item.title) + '</a></h3>' +
          (summaryOf(item) ? '<p class="lede">' + U.escape(summaryOf(item)) + '</p>' : '') +
          '<div class="featured-cta">' +
            '<a class="btn" href="' + G.detailHref(item) + '">Read Full Update</a>' +
            G.renderSourceLink(item, 'Official Source') +
          '</div>' +
        '</div>' +
        '<aside class="featured-rail">' +
          '<div class="rail-row"><span class="rail-key">Department / Ministry</span>' +
            '<span class="rail-val">' + U.escape(item.department || 'Not stated') + '</span></div>' +
          '<div class="rail-row"><span class="rail-key">Published</span>' +
            '<span class="rail-val">' + U.escape(U.formatDate(item.published_date)) + '</span></div>' +
          '<div class="rail-row"><span class="rail-key">Level</span>' +
            '<span class="rail-val">' + U.escape(item.state_level || 'Central') + '</span></div>' +
          '<div class="rail-row"><span class="rail-key">Verification</span>' +
            '<span class="rail-val">' + G.renderTrust(item) + '</span></div>' +
        '</aside>' +
      '</article>';
  }

  function cardHtml(item) {
    return '' +
      '<article class="card"' + G.catAttr(item) + '>' +
        G.renderThumb(item) +
        '<span class="cat-tag">' + U.escape(item.category || 'Other') + '</span>' +
        '<h3><a href="' + G.detailHref(item) + '">' + U.escape(item.title) + '</a></h3>' +
        (summaryOf(item) ? '<p>' + U.escape(summaryOf(item)) + '</p>' : '') +
        '<div class="card-foot">' +
          metaLine(item) +
          G.renderTrust(item) +
        '</div>' +
      '</article>';
  }

  function compactHtml(item) {
    return '' +
      '<li><div class="compact-row"' + G.catAttr(item) + '>' +
        '<div>' +
          '<h3><a href="' + G.detailHref(item) + '">' + U.escape(item.title) + '</a></h3>' +
          (summaryOf(item) ? '<p>' + U.escape(summaryOf(item)) + '</p>' : '') +
          metaLine(item) +
        '</div>' +
        '<div class="compact-side">' +
          '<span class="cat-tag">' + U.escape(item.category || 'Other') + '</span>' +
          G.renderTrust(item) +
        '</div>' +
      '</div></li>';
  }

  /* --- Government Updates page ------------------------------------------- */

  function renderChips(meta) {
    var box = document.getElementById('category-chips');
    if (!box) return;
    var counts = {};
    (meta.categories || []).forEach(function (row) {
      counts[row.category] = row.count;
    });
    var names = ['All'].concat((meta.categories || []).map(function (r) {
      return r.category;
    }));

    // The container also holds the static "Category" label, so preserve it
    // instead of overwriting the whole element.
    var label = box.querySelector('.filter-label');
    var labelHtml = label ? label.outerHTML : '';

    box.innerHTML = labelHtml + names.map(function (name) {
      var pressed = filters.category === name;
      var count = name === 'All' ? '' :
        '<span class="chip-count">' + (counts[name] || 0) + '</span>';
      return '<button type="button" class="chip" data-category="' + U.escape(name) +
             '" aria-pressed="' + pressed + '">' + U.escape(name) + count + '</button>';
    }).join('');

    box.querySelectorAll('.chip').forEach(function (chip) {
      chip.addEventListener('click', function () {
        filters.category = chip.getAttribute('data-category');
        writeFiltersToUrl(false);
        syncControls();
        loadList();
      });
    });
  }

  function renderStateToggle() {
    var box = document.getElementById('state-chips');
    if (!box) return;
    box.querySelectorAll('.chip').forEach(function (chip) {
      chip.addEventListener('click', function () {
        filters.state = chip.getAttribute('data-state');
        writeFiltersToUrl(false);
        syncControls();
        loadList();
      });
    });
  }

  function syncControls() {
    document.querySelectorAll('#category-chips .chip').forEach(function (chip) {
      chip.setAttribute('aria-pressed',
        String(chip.getAttribute('data-category') === filters.category));
    });
    document.querySelectorAll('#state-chips .chip').forEach(function (chip) {
      chip.setAttribute('aria-pressed',
        String(chip.getAttribute('data-state') === filters.state));
    });
    var input = document.getElementById('search-input');
    if (input && input.value !== filters.search) input.value = filters.search;
  }

  /* The element carries a leading inline SVG, so replace only its text and
     leave the icon in place. */
  function setLabelText(el, text) {
    var node = null;
    for (var i = 0; i < el.childNodes.length; i++) {
      if (el.childNodes[i].nodeType === 3 && el.childNodes[i].textContent.trim()) {
        node = el.childNodes[i];
        break;
      }
    }
    if (node) {
      node.textContent = ' ' + text;
    } else {
      el.appendChild(document.createTextNode(' ' + text));
    }
  }

  function renderLastChecked(meta) {
    var el = document.getElementById('last-checked');
    if (!el) return;
    if (G.state.offline) {
      setLabelText(el, 'Last checked: unavailable (API offline)');
      return;
    }
    // Phrased as an observation. The interval is a target, not a promise.
    setLabelText(el, 'Last checked ' + U.relativeTime(meta.last_checked) +
      (meta.freshness_minutes
        ? ' · sources re-checked at most every ' + meta.freshness_minutes + ' min'
        : ''));
  }

  function loadList() {
    var target = document.getElementById('updates');
    if (!target) return;
    target.setAttribute('aria-busy', 'true');

    G.api.getNews({
      category: filters.category,
      state: filters.state,
      search: filters.search,
      limit: G.config.PAGE_SIZE
    }).then(function (data) {
      var items = data.results || [];
      var banners = document.getElementById('banners');
      if (banners) banners.innerHTML = G.renderBanners();

      var countEl = document.getElementById('result-count');
      if (countEl) {
        countEl.textContent = data.total === 0
          ? 'No updates match'
          : 'Showing ' + items.length + ' of ' + data.total + ' updates';
      }

      if (!items.length) {
        target.innerHTML =
          '<div class="state-box"><h3>No updates found</h3>' +
          '<p>Try a different category, or clear the search.</p>' +
          '<p><button type="button" class="btn btn-secondary" id="clear-filters">' +
          'Clear all filters</button></p></div>';
        var clear = document.getElementById('clear-filters');
        if (clear) {
          clear.addEventListener('click', function () {
            filters = { category: 'All', state: 'All', search: '' };
            writeFiltersToUrl(false);
            syncControls();
            loadList();
          });
        }
        target.setAttribute('aria-busy', 'false');
        return;
      }

      // Newspaper hierarchy: 1 featured, then up to 4 medium cards, then the
      // rest as compact rows.
      var featured = items[0];
      var cards = items.slice(1, 5);
      var compact = items.slice(5);

      var html = featuredHtml(featured);

      if (cards.length) {
        html += '<div class="section-rule"><h2>Latest Government Updates</h2>' +
                '<span class="rule-note">' + cards.length + ' shown</span></div>';
        html += '<div class="card-grid">' + cards.map(cardHtml).join('') + '</div>';
      }
      if (compact.length) {
        html += '<div class="section-rule"><h2>More Updates</h2>' +
                '<span class="rule-note">' + compact.length + ' more</span></div>';
        html += '<ul class="compact-list">' + compact.map(compactHtml).join('') + '</ul>';
      }

      target.innerHTML = html;
      target.setAttribute('aria-busy', 'false');
    });
  }

  function initUpdatesPage() {
    readFiltersFromUrl();

    var input = document.getElementById('search-input');
    if (input) {
      input.value = filters.search;
      input.addEventListener('input', U.debounce(function () {
        filters.search = input.value.trim();
        writeFiltersToUrl(true);
        loadList();
      }, 250));
    }

    var form = document.getElementById('search-form');
    if (form) {
      form.addEventListener('submit', function (event) {
        event.preventDefault();
        filters.search = input ? input.value.trim() : '';
        writeFiltersToUrl(false);
        loadList();
      });
    }

    // Back/forward restores the previous filter view.
    window.addEventListener('popstate', function () {
      readFiltersFromUrl();
      syncControls();
      loadList();
    });

    renderStateToggle();

    // One meta call, one list call. No polling after this point.
    G.api.getMeta().then(function (meta) {
      renderChips(meta);
      renderStateToggle();
      renderLastChecked(meta);
      renderHeaderStatus(meta.configured_sources);
      syncControls();
      loadList();
    });
  }

  /* --- Homepage: header status, hero figures, category tiles ------------- */

  /* The utility strip shows whether the API answered, using state the api
     layer has already recorded. */
  function renderHeaderStatus(sourceCount) {
    var box = document.getElementById('strip-status');
    if (!box) return;
    var label = box.querySelector('.status-text');
    if (!label) return;
    if (G.state.offline) {
      box.classList.add('is-offline');
      label.textContent = 'API offline · cached snapshot';
      return;
    }
    box.classList.remove('is-offline');
    label.textContent = (sourceCount || 0) + ' official sources · live';
  }

  function renderHeroStats(meta, total) {
    var box = document.getElementById('hero-stats');
    if (!box) return;
    var cats = (meta.categories || []).length;
    var unknown = '—';
    var stats = [
      { n: total != null ? total : unknown, k: 'Updates held' },
      { n: cats || unknown, k: 'Categories' },
      // Not derivable from the snapshot: only the API knows these.
      { n: G.state.offline ? unknown : (meta.configured_sources || unknown),
        k: 'Official sources' },
      { n: G.state.offline ? unknown : (meta.freshness_minutes || unknown),
        k: 'Min check interval' }
    ];
    box.innerHTML = stats.map(function (s) {
      return '<div class="stat"><span class="stat-num">' + U.escape(String(s.n)) +
             '</span><span class="stat-key">' + U.escape(s.k) + '</span></div>';
    }).join('');

    var foot = document.getElementById('hero-rail-note');
    if (foot) {
      var text = G.state.offline
        ? 'Figures unavailable while the API is offline; showing the cached snapshot.'
        : 'Last checked ' + U.relativeTime(meta.last_checked) +
          '. The interval is a check target, not a guarantee.';
      var node = foot.querySelector('.note-text');
      if (node) node.textContent = text;
    }
  }

  /* Tiles route into the existing filtered views (news.html?category=...). */
  function renderCategoryTiles(meta) {
    var box = document.getElementById('cat-tiles');
    if (!box) return;
    var rows = (meta.categories || []).filter(function (r) { return r.count > 0; });
    if (!rows.length) { box.innerHTML = ''; return; }
    box.innerHTML = rows.map(function (r) {
      return '<a class="cat-tile" data-cat="' + U.escape(r.category) + '" href="news.html?category=' +
             encodeURIComponent(r.category) + '">' +
             '<span class="cat-name">' + U.escape(r.category) + '</span>' +
             '<span class="cat-n">' + U.escape(String(r.count)) + '</span></a>';
    }).join('');

    var note = document.getElementById('cat-note');
    if (note) note.textContent = rows.length + ' categories in use';
  }

  function initHome() {
    var target = document.getElementById('home-updates');
    if (!target) return;

    G.api.getNews({ limit: 3 }).then(function (data) {
      var items = data.results || [];
      var banners = document.getElementById('banners');
      if (banners) banners.innerHTML = G.renderBanners();

      if (!items.length) {
        target.innerHTML =
          '<li style="padding:20px">No updates available yet. ' +
          'Run the collector to load government updates.</li>';
        return;
      }

      target.innerHTML = items.map(function (item, index) {
        return '' +
          '<li' + G.catAttr(item) + '>' +
            '<span class="num">' + ('0' + (index + 1)).slice(-2) + '</span>' +
            '<div>' +
              '<h3><a href="' + G.detailHref(item) + '">' + U.escape(item.title) + '</a></h3>' +
              metaLine(item) +
              '<div class="row-trust">' + G.renderTrust(item) + '</div>' +
            '</div>' +
          '</li>';
      }).join('');

      var stamp = document.getElementById('home-last-checked');
      if (stamp) {
        stamp.textContent = G.state.offline
          ? 'API offline — showing cached snapshot'
          : 'Last checked ' + U.relativeTime(data.last_checked);
      }

      // One meta call for the hero figures and the category tiles. Still no
      // polling: this runs once, on load.
      G.api.getMeta().then(function (meta) {
        renderHeaderStatus(meta.configured_sources);
        renderHeroStats(meta, data.total);
        renderCategoryTiles(meta);
        // hasCached is only known after the meta call, so repaint the banners.
        if (banners) banners.innerHTML = G.renderBanners();
      });
    });
  }

  /* --- Detail page ------------------------------------------------------- */

  /* "Important Points" are derived from the stored content by splitting it
     into sentences. Nothing is invented: if there is no content beyond the
     summary, the section is simply not rendered. */
  function importantPoints(item) {
    var text = (item.content || '').trim();
    if (!text || text === item.summary) return [];
    var sentences = text.split(/(?<=[.!?])\s+/).filter(function (s) {
      return s.trim().length > 40;
    });
    return sentences.slice(0, 5);
  }

  function initDetailPage() {
    var target = document.getElementById('article');
    if (!target) return;

    var id = U.qs('id');
    if (!id) {
      target.innerHTML = '<div class="state-box"><h3>No update selected</h3>' +
        '<p><a href="news.html">Back to Government Updates</a></p></div>';
      return;
    }

    G.api.getNewsById(id).then(function (item) {
      var banners = document.getElementById('banners');

      if (!item) {
        if (banners) banners.innerHTML = G.renderBanners();
        target.innerHTML = '<div class="state-box"><h3>Update not found</h3>' +
          '<p>No government update exists with that reference.</p>' +
          '<p><a class="btn" href="news.html">Back to Government Updates</a></p></div>';
        return;
      }

      G.state.hasCached = item.data_origin === 'cached';
      if (banners) banners.innerHTML = G.renderBanners();

      document.title = item.title + ' — GovEase';

      var points = importantPoints(item);
      var url = U.safeUrl(item.source_url);

      var html = '' +
        '<article class="article"' + G.catAttr(item) + '>' +
          '<span class="cat-tag">' + U.escape(item.category || 'Other') + '</span>' +
          '<h1>' + U.escape(item.title) + '</h1>' +
          '<div class="article-meta">' +
            '<div><span class="rail-key">Department / Ministry</span>' +
              '<span class="rail-val">' + U.escape(item.department || 'Not stated') + '</span></div>' +
            '<div><span class="rail-key">Published</span>' +
              '<span class="rail-val">' + U.escape(U.formatDate(item.published_date)) + '</span></div>' +
            '<div><span class="rail-key">Last verified</span>' +
              '<span class="rail-val">' +
                // A snapshot row carries no poll timestamp of its own, so it
                // must not be shown a "last verified" date it never earned.
                (item.last_checked
                  ? U.escape(U.formatDate(item.last_checked))
                  : 'Not recorded (cached snapshot)') +
              '</span></div>' +
            '<div><span class="rail-key">Level</span>' +
              '<span class="rail-val">' + U.escape(item.state_level || 'Central') + '</span></div>' +
            '<div><span class="rail-key">Source</span>' +
              '<span class="rail-val">' + U.escape(item.source_name || 'Not stated') + '</span></div>' +
            '<div><span class="rail-key">First seen</span>' +
              '<span class="rail-val">' +
                (item.detected_at
                  ? U.escape(U.formatDate(item.detected_at))
                  : 'Not recorded') +
              '</span></div>' +
            '<div><span class="rail-key">Category</span>' +
              '<span class="rail-val">' + U.escape(item.category || 'Other') + '</span></div>' +
          '</div>' +
          '<div class="article-trust">' + G.renderTrust(item) + '</div>' +
          (summaryOf(item)
            ? '<h2>Summary</h2><p>' + U.escape(summaryOf(item)) + '</p>'
            : '');

      if (points.length) {
        html += '<h2>Important Points</h2><ul>' +
          points.map(function (p) { return '<li>' + U.escape(p.trim()) + '</li>'; }).join('') +
          '</ul>';
      }

      html += '<div class="source-box"><h2>Official Source</h2>';
      if (url) {
        html += '<p class="source-note">GovEase is not the authority for this ' +
                'information. Read the original notification on the ' +
                'department’s own website before acting on it.</p>' +
                '<p><strong>Source:</strong> ' + U.escape(item.source_name || '') + '</p>' +
                G.renderSourceLink(item, 'View Official Notification');
      } else {
        html += '<p class="source-note">No source link is recorded for this ' +
                'item. Look it up on the issuing department’s own website ' +
                'before relying on it.</p>';
      }
      html += '</div></article>';

      target.innerHTML = html;
    });
  }

  G.news = {
    initUpdatesPage: initUpdatesPage,
    initHome: initHome,
    initDetailPage: initDetailPage
  };

  document.addEventListener('DOMContentLoaded', function () {
    initHome();
    initUpdatesPage();
    initDetailPage();
  });

})(window.GovEase);
