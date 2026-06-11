// login.html page logic
var LoginPage = {
    cl: null, _p: null, _c: null, _err: null,

    init: function() {
        var self = this;
        this._p = document.getElementById('pl');
        this._c = document.getElementById('chat');
        this._err = document.getElementById('err');
        this._newClient();
        document.getElementById('wsUrlInput').value = DemoConfig.WS_URL;
    },

    _newClient: function() {
        if (this.cl) this.cl.close();
        this.cl = new WsClient(DemoConfig.WS_URL);
        window.__client = this.cl;
        var self = this;
        this.cl.onLog = function(e) { U.proto(self._p, e); };
        this.cl.onState = function(s) { U.conn(document.getElementById('st'), s === 'connected'); };
        this.cl.onLogin = function(user, token) {
            State.user(user); State.token(token);
            U.badge(document.getElementById('bd'), user);
            U.tok(document.getElementById('tk'), token);
            U.sys(self._c, 'Logged in: ' + user);
            document.getElementById('loginSection').style.display = 'none';
            self._err.textContent = '';
        };
        this.cl.onMsg = function(m) {
            if (m.msg_type === 'register' && m.code === 200) {
                U.sys(self._c, 'Registered: ' + ((m.content && m.content.username) || ''));
                self._err.textContent = 'OK: Registered';
            }
            if (m.msg_type === 'error') {
                self._err.textContent = (m.code || '') + ' ' + (m.err_msg || '');
                U.sys(self._c, 'Error: ' + m.err_msg);
            }
        };
    },

    ensure: function() {
        if (this.cl && this.cl.connected) return Promise.resolve();
        this._newClient();
        return this.cl.connect();
    },

    register: function() {
        var u = document.getElementById('u').value.trim();
        var p = document.getElementById('p').value;
        this._err.textContent = '';
        var self = this;
        this.ensure().then(function() { self.cl.register(u, p); });
    },

    login: function() {
        var u = document.getElementById('u').value.trim();
        var p = document.getElementById('p').value;
        this._err.textContent = '';
        var self = this;
        this.ensure().then(function() { self.cl.login(u, p); });
    },

    logout: function() {
        State.logout();
        if (this.cl) this.cl.close();
        this.cl = null;
        U.clear(this._c); U.clear(this._p);
        U.badge(document.getElementById('bd'), '');
        U.tok(document.getElementById('tk'), '');
        U.conn(document.getElementById('st'), false);
        this._err.textContent = '';
        document.getElementById('loginSection').style.display = 'block';
    }
};
