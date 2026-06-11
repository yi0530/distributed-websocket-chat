// Private chat module — receives messages via AppPage dispatch
var PrivMod = {
    cl: null, cid: null, target: null,

    render: function(area, client) {
        this.cl = client;
        this.cid = State.privConv();
        this.target = State.target();
        area.innerHTML =
            '<div class="toolbar">' +
            '<input id="pv-target" placeholder="目标用户" value="' + (this.target || 'user002') + '" style="width:120px">' +
            '<button onclick="PrivMod.startChat()">发起私聊</button>' +
            '<span class="hint" id="pv-label">' + (this.target ? '与 ' + this.target + ' 聊天中' : '') + '</span>' +
            '</div>' +
            '<div class="chat-msgs" id="pv-msgs"></div>' +
            '<div class="chat-input"><input id="pv-input" placeholder="输入私聊消息..." onkeydown="if(event.key===\'Enter\')PrivMod.send()"><button onclick="PrivMod.send()">发送</button></div>';
    },

    handleMsg: function(m) {
        var mt = m.msg_type;
        if (mt === 'private_conversation_created' && m.code === 200) {
            this.cid = m.content.conversation_id;
            State.privConv(this.cid);
            var parts = (m.content && m.content.participants) || [];
            this.target = parts.find(function(x) { return x !== State.user(); }) || document.getElementById('pv-target').value.trim();
            State.target(this.target);
            var el = document.getElementById('pv-label');
            if (el) el.textContent = '与 ' + this.target + ' 聊天中';
            U.sys(document.getElementById('pv-msgs'), '已建立与 ' + this.target + ' 的私聊');
        }
        if (mt === 'private_chat') {
            var own = (m.content && m.content.from_user_id) === State.user();
            U.msg(document.getElementById('pv-msgs'), m.content, own);
        }
        if (mt === 'error') {
            U.sys(document.getElementById('pv-msgs'), m.err_msg || '');
        }
    },

    handleAck: function(msgId, status, rtt) {
        U.sys(document.getElementById('pv-msgs'), 'ACK ' + status + (rtt ? ' rtt=' + rtt + 'ms' : ''));
    },

    startChat: function() {
        if (!AppPage.appReady) return;
        var t = document.getElementById('pv-target').value.trim();
        if (t) this.cl.createPrivConv(t);
    },
    send: function() {
        if (!AppPage.appReady || !this.cid) return;
        var t = document.getElementById('pv-input').value.trim();
        if (!t) return;
        this.cl.sendPrivMsg(this.cid, t, true);
        document.getElementById('pv-input').value = '';
    }
};
