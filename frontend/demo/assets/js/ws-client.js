// WebSocket client with ACK tracking and protocol logging
function WsClient(url) {
    this.url = url || DemoConfig.WS_URL;
    this.ws = null;
    this.connected = false;
    this._closed = false;
    this._ack = {};
    this._eid = 0;
    this.onLog = null;
    this.onMsg = null;
    this.onState = null;
    this.onAck = null;
    this.onLogin = null;
    this._loginUser = null;
}
WsClient.prototype.connect = function() {
    var self = this;
    return new Promise(function(resolve, reject) {
        self._log('SYSTEM', 'connect', 'Connecting ' + self.url);
        self.ws = new WebSocket(self.url);

        var settled = false;
        var timeout = DemoConfig.CONNECT_TIMEOUT_MS || 8000;
        var timer = setTimeout(function() {
            if (settled) return;
            settled = true;
            try { self.ws && self.ws.close(); } catch(e) {}
            self.connected = false;
            self._fireState('error');
            self._log('ERROR', 'timeout', 'WebSocket connect timeout (' + timeout + 'ms)');
            reject(new Error('connect timeout'));
        }, timeout);

        self.ws.onopen = function() {
            clearTimeout(timer);
            if (settled) return;
            settled = true;
            self.connected = true;
            self._fireState('connected');
            self._log('SYSTEM', 'connect', 'Connected');
            resolve();
        };
        self.ws.onmessage = function(e) { self._onmsg(e.data); };
        self.ws.onclose = function(e) {
            clearTimeout(timer);
            if (settled) {
                self.connected = false;
                var reason = 'code=' + e.code + ' reason=' + (e.reason || '') + ' wasClean=' + e.wasClean;
                self._log('SYSTEM', 'close', 'Closed ' + reason);
                self._fireState('disconnected');
            } else {
                settled = true;
                self.connected = false;
                self._log('SYSTEM', 'close', 'Closed code=' + e.code);
                self._fireState('error');
                reject(new Error('connect closed code=' + e.code));
            }
        };
        self.ws.onerror = function() {
            clearTimeout(timer);
            if (settled) return;
            settled = true;
            self._log('ERROR', 'error', 'WebSocket error');
            self._fireState('error');
            reject(new Error('connect error'));
        };
    });
};
WsClient.prototype.close = function() {
    if (this._closed) return;
    this._closed = true;
    if (this.ws) { try { this.ws.close(1000); } catch(e) {} this.ws = null; }
    this.connected = false; this._ack = {}; this._fireState('disconnected');
};
WsClient.prototype._send = function(msg) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) { this._log('ERROR','send','Not connected'); return false; }
    var raw = JSON.stringify(msg); this.ws.send(raw);
    var mt = msg.msg_type, s = mt;
    if (msg.from) s += ' u=' + msg.from;
    if (msg.conversation_id) s += ' cid=' + msg.conversation_id.slice(0,8);
    if (msg.payload && msg.payload.text) s += ' "' + msg.payload.text.slice(0,20) + '"';
    this._log('SEND', mt, s, msg);
    return true;
};
WsClient.prototype._onmsg = function(raw) {
    var self = this;
    try { var msg = JSON.parse(raw); } catch(e) { this._log('ERROR','parse','Bad JSON'); return; }
    var mt = msg.msg_type, s = mt + ' code=' + (msg.code||'?');
    if (mt === 'ack') {
        var oid = (msg.content && msg.content.original_msg_id) || '';
        var st = (msg.content && msg.content.status) || '?';
        s += ' ack_for=' + oid.slice(0,16);
        if (self._ack[oid]) { var rtt = Date.now() - self._ack[oid].time; self._ack[oid].status = st; self._ack[oid].rtt = rtt; s += ' rtt=' + rtt + 'ms'; if (self.onAck) self.onAck(oid, st, rtt); }
    }
    if (mt === 'login' && msg.code === 200) {
        s += ' token=' + ((msg.content&&msg.content.token)||'').slice(0,12)+'...';
        if (self._loginUser && self.onLogin) self.onLogin(self._loginUser, (msg.content&&msg.content.token)||'');
        self._loginUser = null;
    }
    if (mt === 'register' && msg.code === 200) { s += ' ok'; }
    if (mt === 'room_created' && msg.code === 200) { s += ' rid=' + ((msg.content&&msg.content.conversation_id)||'').slice(0,8); }
    if (mt === 'room_chat' || mt === 'private_chat') { var t = (msg.content&&msg.content.text)||''; s += ' from='+(msg.content&&msg.content.from_user_id||'?')+' "'+t.slice(0,20)+'"'; }
    if (mt === 'error') { s += ' ' + (msg.err_msg||''); }
    this._log('RECV', mt, s, msg);
    if (this.onMsg) this.onMsg(msg);
};
WsClient.prototype._log = function(dir, type, summary, raw) {
    this._eid++;
    var e = { id: this._eid, time: new Date().toISOString().slice(11,23), dir: dir, type: type, summary: summary, raw: raw||null };
    if (this.onLog) this.onLog(e);
};
WsClient.prototype._fireState = function(s) { if (this.onState) this.onState(s); };

// Public API
WsClient.prototype.register = function(u,p) { return this._send(Proto.register(u,p)); };
WsClient.prototype.login = function(u,p) { this._loginUser = u; return this._send(Proto.login(u,p)); };
WsClient.prototype.createRoom = function(name) { return this._send(Proto.createRoom(name||'Room')); };
WsClient.prototype.joinRoom = function(rid) { return this._send(Proto.joinRoom(rid)); };
WsClient.prototype.sendRoomMsg = function(rid, text, ack) {
    var msg = Proto.roomChat(rid, text, ack);
    if (ack !== false) this._ack[msg.msg_id] = { time: Date.now(), status: 'pending' };
    return this._send(msg);
};
WsClient.prototype.createPrivConv = function(target) { return this._send(Proto.createPrivConv(target)); };
WsClient.prototype.sendPrivMsg = function(cid, text, ack) {
    var msg = Proto.privateChat(cid, text, ack);
    if (ack !== false) this._ack[msg.msg_id] = { time: Date.now(), status: 'pending' };
    return this._send(msg);
};
WsClient.prototype.listRooms = function() { return this._send(Proto.listRooms()); };
WsClient.prototype.listMyConversations = function() { return this._send(Proto.listMyConversations()); };
WsClient.prototype.pending = function() { return this._ack; };
