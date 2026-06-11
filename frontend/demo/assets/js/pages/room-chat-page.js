// room-chat.html page logic
var RoomChatPage = {
    cl: null, room: null, _c: null, _p: null,

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
            if (mt === 'room_created' && m.code === 200) {
                self.room = m.content.conversation_id; State.room(self.room);
                U.sys(self._c, 'Room: ' + self.room.slice(0, 12));
                document.getElementById('rm').textContent = 'Room: ' + self.room.slice(0, 12);
            }
            if (mt === 'room_joined' && m.code === 200) {
                self.room = m.content.conversation_id; State.room(self.room);
                U.sys(self._c, 'Joined: ' + self.room.slice(0, 12));
                document.getElementById('rm').textContent = 'Room: ' + self.room.slice(0, 12);
            }
            if (mt === 'room_chat') {
                var own = (m.content && m.content.from_user_id) === State.user();
                U.msg(self._c, m.content, own);
            }
            if (mt === 'error') U.sys(self._c, 'Error: ' + (m.err_msg || ''));
        };
        this.cl.onAck = function(id, st, rtt) {
            U.sys(self._c, 'ACK ' + st + ' rtt=' + (rtt || '?') + 'ms');
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

    createRoom: function() {
        var self = this;
        this.ensure().then(function() { self.cl.createRoom(document.getElementById('rn').value.trim() || 'Room'); });
    },

    joinRoom: function() {
        var self = this;
        this.ensure().then(function() { self.cl.joinRoom(document.getElementById('rj').value.trim()); });
    },

    sendChat: function() {
        if (!this.room) return;
        var t = document.getElementById('ci').value.trim(); if (!t) return;
        var self = this;
        this.ensure().then(function() { self.cl.sendRoomMsg(self.room, t, true); });
        document.getElementById('ci').value = '';
    },

    logout: function() {
        State.logout(); this.room = null;
        if (this.cl) this.cl.close(); this.cl = null;
        U.clear(this._c); U.clear(this._p);
        U.badge(document.getElementById('bd'), '');
        U.conn(document.getElementById('st'), false);
        document.getElementById('rm').textContent = 'No room';
    }
};
