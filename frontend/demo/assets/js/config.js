// Demo configuration
const DemoConfig = {
    APP_VERSION: 1,
    ACK_TIMEOUT_MS: 10000,
    CONNECT_TIMEOUT_MS: 8000,
    LOGIN_TIMEOUT_MS: 8000,

    get WS_URL() { return getWsUrl(); },
    set WS_URL(v) { setWsUrl(v); },
    setWsUrl: function(v) { setWsUrl(v); },
    getWsUrl: function() { return getWsUrl(); },
};

function getWsUrl() {
    // Priority: URL param ?ws= (from index page jump) > current-window sessionStorage > default
    var p = new URLSearchParams(location.search);
    if (p.has('ws')) {
        var url = p.get('ws');
        try { sessionStorage.setItem('demo_ws_url', url); } catch(e) {}
        return url;
    }
    try {
        var saved = sessionStorage.getItem('demo_ws_url');
        if (saved) return saved;
    } catch(e) {}
    return 'ws://127.0.0.1:8765';
}

function setWsUrl(url) {
    try { sessionStorage.setItem('demo_ws_url', url); } catch(e) {}
}
