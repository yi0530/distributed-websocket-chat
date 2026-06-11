// Demo configuration
const DemoConfig = {
    get WS_URL() {
        const p = new URLSearchParams(location.search);
        return p.get('ws') || 'ws://127.0.0.1:8768';
    },
    APP_VERSION: 1,
    ACK_TIMEOUT_MS: 10000,
};
