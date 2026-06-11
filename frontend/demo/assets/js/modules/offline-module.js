// Offline message module
var OffMod = {
    cl: null, cid: null, target: null, _expect: false, role: '',

    render: function(area, client) {
        this.cl = client; this.cid = State.privConv(); this.target = State.target();
        var self = this;
        area.innerHTML =
            '<div class="toolbar">' +
            '<input id="of-target" placeholder="Target user" value="' + (this.target || 'user002') + '" style="width:100px">' +
            '<button onclick="OffMod.startChat()" class="green">1. Start Chat</button>' +
            '<button onclick="OffMod.disconnect()" style="background:#f59e0b;">2. Go Offline</button>' +
            '<button onclick="OffMod.reconnect()" style="background:#7c3aed;">3. Reconnect &amp; Login</button>' +
            '<span class="hint" id="of-hint">Step 1: Start chat, then go offline</span>' +
            '</div>' +
            '<div class="chat-msgs" id="of-msgs"></div>' +
            '<div class="chat-input"><input id="of-input" placeholder="Message (goes to offline user)..."><button onclick="OffMod.send()">Send</button></div>';
        var ocb = this.cl.onMsg;
        this.cl.onMsg = function(m) {
            if (ocb) ocb(m);
            var mt = m.msg_type;
            if (mt === 'private_conversation_created' && m.code === 200) {
                self.cid = m.content.conversation_id; State.privConv(self.cid);
                var parts = (m.content && m.content.participants) || [];
                self.target = parts.find(function(x) { return x !== State.user(); }) || document.getElementById('of-target').value.trim();
                State.target(self.target);
                U.sys(document.getElementById('of-msgs'), 'Chat with ' + self.target);
                document.getElementById('of-hint').textContent = 'Ready. Now click Go Offline';
            }
            if (mt === 'private_chat') {
                var own = (m.content && m.content.from_user_id) === State.user();
                var extra = {};
                if (!own && self._expect) { extra.offline = true; self._expect = false; document.getElementById('of-hint').textContent = 'Offline message received!'; U.sys(document.getElementById('of-msgs'), '[Offline delivery complete]'); }
                U.msg(document.getElementById('of-msgs'), m.content, own, extra);
            }
            if (mt === 'error') U.sys(document.getElementById('of-msgs'), m.err_msg || '');
        };
    },

    startChat: function() {
        var t = document.getElementById('of-target').value.trim();
        this.cl.createPrivConv(t);
    },
    disconnect: function() {
        if (this.cl) this.cl.close();
        U.conn(document.getElementById('topConn'), false);
        U.sys(document.getElementById('of-msgs'), '[Disconnected]');
        document.getElementById('of-hint').textContent = 'Offline now. Send message from another window, then click Reconnect & Login';
        this._expect = true;
    },
    reconnect: function() {
        var self = this;
        var u = State.user(), p = State.pwd();
        var nc = new WsClient(DemoConfig.WS_URL);
        window.__client = nc;
        nc.onLog = function(e) { U.proto(document.getElementById('protoPanel'), e); };
        nc.onState = function(s) {
            var el = document.getElementById('topConn');
            el.textContent = s === 'connected' ? '● 已连接' : '○ 未连接';
            el.className = 'top-conn ' + (s === 'connected' ? 'top-ok' : 'top-off');
        };
        var oldMsg = self.cl.onMsg, oldAck = self.cl.onAck;
        nc.connect().then(function() {
            U.sys(document.getElementById('of-msgs'), '[Reconnected]');
            nc.login(u, p);
            nc.onLogin = function() {};
            nc.onMsg = oldMsg;
            nc.onAck = oldAck;
            self.cl = nc;
            AppPage.cl = nc;
        });
    },
    send: function() {
        if (!this.cid) return;
        var t = document.getElementById('of-input').value.trim(); if (!t) return;
        this.cl.sendPrivMsg(this.cid, t, false);
        document.getElementById('of-input').value = '';
        document.getElementById('of-hint').textContent = 'Sent! Receiver: click Reconnect & Login to receive';
    }
};
