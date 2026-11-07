(function() {
    function apply(data) {
        const elements = document.querySelectorAll('[data-stat]');
        elements.forEach(el => {
            const key = el.dataset.stat;
            if (key === "robots") {
                el.textContent = `robots.txt: ${data.respect_robots ? "respected" : "IGNORED"}`;
                el.className = data.respect_robots ? "ok" : "warn";
            } else if (key === "running") {
                el.textContent = data.running ? "running" : "not running";
            } else if (key === "crawl_state") {
                el.textContent = data.crawl_state;
                el.className = `state ${data.crawl_state}`;
            } else if (data[key] !== undefined) {
                el.textContent = String(data[key]);
            }
        });
    }

    function poll() {
        fetch("/api/stats", { credentials: "same-origin" })
            .then(response => {
                if (response.status === 401) {
                    clearInterval(interval);
                } else if (response.ok) {
                    return response.json();
                }
            })
            .then(data => { if (data) apply(data); })
            .catch(() => {});
    }

    const interval = setInterval(poll, 3000);
    poll();
})();

(function() {
    var all = document.querySelector('[data-select-all]');
    if (!all) return;
    all.addEventListener('change', function() {
        document.querySelectorAll('input[name="ids"]').forEach(function(box) { box.checked = all.checked; });
    });
})();
