// private-chat.html page logic
var PrivateChatPage = {
    cl: null, cid: null, target: null, _c: null, _p: null,

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
            }
            if (mt === 'private_chat') {
                var own = (m.content && m.content.from_user_id) === State.user();
                U.msg(self._c, m.content, own);
            }
            if (mt === 'error') U.sys(self._c, 'Error: ' + (m.err_msg || ''));
        };
        this.cl.onAck = function(id, st, rtt) {
            U.sys(self._c, 'ACK ' + st + (rtt ? ' rtt=' + rtt + 'ms' : ''));
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
        this.ensure().then(function() { self.cl.sendPrivMsg(self.cid, t, true); });
        document.getElementById('ci').value = '';
    },

    logout: function() {
        State.logout(); this.cid = null; this.target = null;
        if (this.cl) this.cl.close(); this.cl = null;
        U.clear(this._c); U.clear(this._p);
        U.badge(document.getElementById('bd'), '');
        U.conn(document.getElementById('st'), false);
        document.getElementById('tg').textContent = 'Target: none';
    }
};
