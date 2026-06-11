// offline-message.html page logic
var OfflinePage = {
    cl: null, cid: null, target: null, _c: null, _p: null,
    _expectOffline: false,

    init: function() {
        this._c = document.getElementById('chat');
        this._p = document.getElementById('pl');
        this._newClient();
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
            U.sys(self._c, 'Login: ' + user);
        };
        this.cl.onMsg = function(m) {
            var mt = m.msg_type;
            if (mt === 'private_conversation_created' && m.code === 200) {
                self.cid = m.content.conversation_id;
                var parts = (m.content && m.content.participants) || [];
                self.target = parts.find(function(x) { return x !== State.user(); }) || document.getElementById('tu').value.trim();
                State.privConv(self.cid); State.target(self.target);
                document.getElementById('tg').textContent = 'Target: ' + self.target;
                U.sys(self._c, 'Private chat: ' + self.target);
                document.getElementById('hint').textContent = 'Ready. Disconnect receiver first, then send';
            }
            if (mt === 'private_chat') {
                var from = (m.content && m.content.from_user_id) || '';
                var own = from === State.user();
                var extra = {};
                if (!own && self._expectOffline) {
                    extra.offline = true;
                    self._expectOffline = false;
                    document.getElementById('hint').textContent = 'Offline message received!';
                    U.sys(self._c, '[Offline delivery completed]');
                }
                U.msg(self._c, m.content, own, extra);
            }
            if (mt === 'error') U.sys(self._c, 'Error: ' + (m.err_msg || ''));
        };
    },

    ensure: function() {
        if (this.cl && this.cl.connected) return Promise.resolve();
        this._newClient();
        return this.cl.connect();
    },

    login: function() {
        var u = document.getElementById('u').value.trim();
        var p = document.getElementById('p').value;
        var self = this;
        this.ensure().then(function() { self.cl.login(u, p); });
    },

    startChat: function() {
        var t = document.getElementById('tu').value.trim();
        var self = this;
        this.ensure().then(function() { self.cl.createPrivConv(t); });
    },

    sendMsg: function() {
        if (!this.cid) return;
        var t = document.getElementById('ci').value.trim(); if (!t) return;
        var self = this;
        this.ensure().then(function() { self.cl.sendPrivMsg(self.cid, t, false); });
        document.getElementById('ci').value = '';
        document.getElementById('hint').textContent = 'Sent! Now receiver reconnects to get offline message';
    },

    disconnect: function() {
        if (this.cl) this.cl.close();
        U.conn(document.getElementById('st'), false);
        U.sys(this._c, '[Disconnected - you are now offline]');
        document.getElementById('hint').textContent = 'Offline now. Wait for sender to send, then click Reconnect & Login';
        this._expectOffline = true;
    },

    reconnectAndLogin: function() {
        var u = document.getElementById('u').value.trim();
        var p = document.getElementById('p').value;
        var self = this;
        this._newClient();
        this.cl.connect().then(function() {
            U.sys(self._c, '[Reconnected]');
            self.cl.login(u, p);
        }).catch(function() {
            U.sys(self._c, '[Reconnect failed]');
        });
    },

    logout: function() {
        State.logout(); this.cid = null; this.target = null; this._expectOffline = false;
        if (this.cl) this.cl.close(); this.cl = null;
        U.clear(this._c); U.clear(this._p);
        U.badge(document.getElementById('bd'), '');
        U.conn(document.getElementById('st'), false);
        document.getElementById('tg').textContent = 'Target: none';
        document.getElementById('hint').textContent = 'Step: Login first';
    }
};
