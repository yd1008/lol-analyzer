// Auto-dismiss flash messages after 5 seconds
document.addEventListener('DOMContentLoaded', function () {
    var flashes = document.querySelectorAll('.flash');
    flashes.forEach(function (flash) {
        setTimeout(function () {
            flash.style.animation = 'slideIn 0.3s ease reverse';
            setTimeout(function () { flash.remove(); }, 300);
        }, 5000);
    });

    // ---- Dashboard match list logic ----
    var matchList = document.getElementById('match-list');
    if (!matchList) return;

    var loadMoreBtn = document.getElementById('load-more-btn');
    var loadMoreContainer = document.getElementById('load-more-container');
    var filterBar = document.getElementById('match-filter-bar');
    var currentOffset = window.__initialMatchCount || 0;
    var currentQueue = '';
    var csrfToken = document.querySelector('meta[name="csrf-token"]');
    csrfToken = csrfToken ? csrfToken.getAttribute('content') : '';

    function escapeHtml(str) {
        var div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    var POSITION_MAP = {TOP: 'TOP', JUNGLE: 'JGL', MIDDLE: 'MID', BOTTOM: 'BOT', UTILITY: 'SUP'};

    function renderMatchBox(m) {
        var winClass = m.win ? 'match-win' : 'match-loss';
        var resultText = m.win ? 'Victory' : 'Defeat';
        var queueHtml = m.queue_type ? '<span class="match-queue">' + escapeHtml(m.queue_type) + '</span>' : '';
        var positionBadge = m.player_position && POSITION_MAP[m.player_position]
            ? '<span class="position-badge">' + POSITION_MAP[m.player_position] + '</span>'
            : '';

        var enemiesHtml = '';
        if (m.enemies && m.enemies.length > 0) {
            enemiesHtml = '<div class="match-box-enemies"><span class="match-box-enemies-label">vs</span>';
            m.enemies.forEach(function (e) {
                var title = escapeHtml((e.summoner_name || '') + '#' + (e.tagline || ''));
                var laneLabel = e.position && POSITION_MAP[e.position]
                    ? '<span class="lane-label">' + POSITION_MAP[e.position] + '</span>'
                    : '';
                enemiesHtml += '<span class="enemy-tag" title="' + title + '">' + laneLabel + escapeHtml(e.champion) + '</span>';
            });
            enemiesHtml += '</div>';
        }

        var aiClass = m.has_llm_analysis ? ' has-analysis' : '';
        var aiText = m.has_llm_analysis ? 'AI Analysis' : 'Run AI Analysis';

        return '<div class="match-box ' + winClass + '" data-match-id="' + m.id + '">' +
            '<div class="match-box-indicator"></div>' +
            '<div class="match-box-main">' +
                '<div class="match-box-header">' +
                    '<span class="match-champion">' + escapeHtml(m.champion) + '</span>' +
                    positionBadge +
                    '<span class="match-result-tag">' + resultText + '</span>' +
                    queueHtml +
                    '<span class="match-duration">' + m.game_duration + 'm</span>' +
                '</div>' +
                '<div class="match-box-stats">' +
                    '<span class="match-kda">' + m.kills + '/' + m.deaths + '/' + m.assists +
                        '<span class="match-kda-ratio">' + m.kda + ' KDA</span></span>' +
                    '<div class="match-stat-pills">' +
                        '<span class="stat-pill">' + m.gold_per_min + ' G/m</span>' +
                        '<span class="stat-pill">' + m.damage_per_min + ' D/m</span>' +
                        '<span class="stat-pill">' + m.vision_score + ' VS</span>' +
                        '<span class="stat-pill">' + m.cs_total + ' CS</span>' +
                    '</div>' +
                '</div>' +
                enemiesHtml +
            '</div>' +
            '<div class="match-box-actions">' +
                '<a href="/dashboard/matches/' + m.id + '" class="btn btn-ghost btn-sm">Details</a>' +
                '<button class="ai-btn' + aiClass + '" data-match-id="' + m.id + '">' + aiText + '</button>' +
            '</div>' +
        '</div>';
    }

    function loadMore() {
        if (!loadMoreBtn) return;
        loadMoreBtn.disabled = true;
        loadMoreBtn.textContent = 'Loading...';

        var url = '/dashboard/api/matches?offset=' + currentOffset + '&limit=10';
        if (currentQueue) url += '&queue=' + encodeURIComponent(currentQueue);

        fetch(url)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                data.matches.forEach(function (m) {
                    matchList.insertAdjacentHTML('beforeend', renderMatchBox(m));
                });
                currentOffset += data.matches.length;

                if (!data.has_more) {
                    if (loadMoreContainer) loadMoreContainer.style.display = 'none';
                } else {
                    loadMoreBtn.disabled = false;
                    loadMoreBtn.textContent = 'Load More';
                }
            })
            .catch(function () {
                loadMoreBtn.disabled = false;
                loadMoreBtn.textContent = 'Load More';
            });
    }

    function filterByQueue(queue) {
        currentQueue = queue;
        currentOffset = 0;
        matchList.innerHTML = '';
        if (loadMoreContainer) {
            loadMoreContainer.style.display = '';
            if (loadMoreBtn) {
                loadMoreBtn.disabled = true;
                loadMoreBtn.textContent = 'Loading...';
            }
        }

        var url = '/dashboard/api/matches?offset=0&limit=10';
        if (queue) url += '&queue=' + encodeURIComponent(queue);

        fetch(url)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.matches.length === 0) {
                    matchList.innerHTML = '<div class="empty-state"><p>No matches found for this filter.</p></div>';
                    if (loadMoreContainer) loadMoreContainer.style.display = 'none';
                    return;
                }
                data.matches.forEach(function (m) {
                    matchList.insertAdjacentHTML('beforeend', renderMatchBox(m));
                });
                currentOffset = data.matches.length;

                if (!data.has_more) {
                    if (loadMoreContainer) loadMoreContainer.style.display = 'none';
                } else {
                    if (loadMoreContainer) loadMoreContainer.style.display = '';
                    if (loadMoreBtn) {
                        loadMoreBtn.disabled = false;
                        loadMoreBtn.textContent = 'Load More';
                    }
                }
            })
            .catch(function () {
                if (loadMoreBtn) {
                    loadMoreBtn.disabled = false;
                    loadMoreBtn.textContent = 'Load More';
                }
            });
    }

    if (loadMoreBtn) {
        loadMoreBtn.addEventListener('click', loadMore);
    }

    if (filterBar) {
        filterBar.addEventListener('click', function (e) {
            var btn = e.target.closest('.filter-btn');
            if (!btn) return;
            filterBar.querySelectorAll('.filter-btn').forEach(function (b) { b.classList.remove('active'); });
            btn.classList.add('active');
            filterByQueue(btn.getAttribute('data-queue'));
        });
    }

    // AI analysis via event delegation
    matchList.addEventListener('click', function (e) {
        var btn = e.target.closest('.ai-btn');
        if (!btn) return;

        var matchId = btn.getAttribute('data-match-id');
        var matchBox = btn.closest('.match-box');

        // Toggle existing panel
        var existingPanel = matchBox.nextElementSibling;
        if (existingPanel && existingPanel.classList.contains('ai-analysis-panel')) {
            existingPanel.remove();
            return;
        }

        btn.disabled = true;
        btn.textContent = 'Analyzing...';

        fetch('/dashboard/api/matches/' + matchId + '/ai-analysis', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
            },
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.error) {
                btn.textContent = 'Error';
                btn.disabled = false;
                setTimeout(function () { btn.textContent = 'Run AI Analysis'; }, 2000);
                return;
            }

            btn.textContent = 'AI Analysis';
            btn.classList.add('has-analysis');
            btn.disabled = false;

            var panel = document.createElement('div');
            panel.className = 'ai-analysis-panel';
            panel.textContent = data.analysis;
            matchBox.insertAdjacentElement('afterend', panel);
        })
        .catch(function () {
            btn.textContent = 'Error';
            btn.disabled = false;
            setTimeout(function () { btn.textContent = 'Run AI Analysis'; }, 2000);
        });
    });
});
