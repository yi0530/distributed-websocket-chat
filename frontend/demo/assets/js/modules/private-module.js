// Private chat module
var PrivMod = {
    cl: null, cid: null, target: null,

    render: function(area, client) {
        this.cl = client; this.cid = State.privConv(); this.target = State.target();
        var self = this;
        area.innerHTML =
            '<div class="toolbar">' +
            '<input id="pv-target" placeholder="Target user" value="' + (this.target || 'user002') + '" style="width:120px">' +
            '<button onclick="PrivMod.startChat()">Start Chat</button>' +
            '<span class="hint" id="pv-label">' + (this.target ? 'Chatting with ' + this.target : '') + '</span>' +
            '</div>' +
            '<div class="chat-msgs" id="pv-msgs"></div>' +
            '<div class="chat-input"><input id="pv-input" placeholder="Private message..."><button onclick="PrivMod.send()">Send</button></div>';
        var ocb = this.cl.onMsg;
        this.cl.onMsg = function(m) {
            if (ocb) ocb(m);
            var mt = m.msg_type;
            if (mt === 'private_conversation_created' && m.code === 200) {
                self.cid = m.content.conversation_id; State.privConv(self.cid);
                var parts = (m.content && m.content.participants) || [];
                self.target = parts.find(function(x) { return x !== State.user(); }) || document.getElementById('pv-target').value.trim();
                State.target(self.target);
                document.getElementById('pv-label').textContent = 'Chatting with ' + self.target;
                U.sys(document.getElementById('pv-msgs'), 'Chat with ' + self.target);
            }
            if (mt === 'private_chat') {
                var own = (m.content && m.content.from_user_id) === State.user();
                U.msg(document.getElementById('pv-msgs'), m.content, own);
            }
            if (mt === 'error') U.sys(document.getElementById('pv-msgs'), m.err_msg || '');
        };
        var oca = this.cl.onAck;
        this.cl.onAck = function(id, st, rtt) {
            if (oca) oca(id, st, rtt);
            U.sys(document.getElementById('pv-msgs'), 'ACK ' + st + (rtt ? ' rtt=' + rtt + 'ms' : ''));
        };
    },

    startChat: function() {
        var t = document.getElementById('pv-target').value.trim();
        this.cl.createPrivConv(t);
    },
    send: function() {
        if (!this.cid) return;
        var t = document.getElementById('pv-input').value.trim(); if (!t) return;
        this.cl.sendPrivMsg(this.cid, t, true);
        document.getElementById('pv-input').value = '';
    }
};
