// Private chat module — messages cached, state recovered, CID-isolated
var PrivMod = {
    cl: null, cid: null, target: null, _msgs: [],

    _recoverState: function(m) {
        // Recover conversation_id and target from a delivered private_chat
        if (!this.cid && m.conversation_id) {
            this.cid = m.conversation_id;
            State.privConv(this.cid);
        }
        var fromId = m.content && m.content.from_user_id;
        var toId = m.content && m.content.to_user_id;
        var me = State.user();
        var other = null;
        if (fromId && fromId !== me) other = fromId;
        else if (toId && toId !== me) other = toId;
        if (other) {
            this.target = other;
            State.target(other);
        } else if (!this.target) {
            this.target = State.target();
        }
        // Update DOM if visible
        var elT = document.getElementById('pv-target');
        if (elT && this.target) elT.value = this.target;
        var elL = document.getElementById('pv-label');
        if (elL && this.target) elL.textContent = '与 ' + this.target + ' 聊天中';
    },

    render: function(area, client) {
        this.cl = client;
        this.cid = State.privConv();
        this.target = State.target();
        area.innerHTML =
            '<div class="toolbar">' +
            '<input id="pv-target" placeholder="目标用户" value="' + (this.target || 'user002') + '" style="width:120px">' +
            '<button id="pv-btn-start" onclick="PrivMod.startChat()">发起私聊</button>' +
            '<span class="hint" id="pv-label">' + (this.target ? '与 ' + this.target + ' 聊天中' : '') + '</span>' +
            '</div>' +
            '<div class="chat-msgs" id="pv-msgs"></div>' +
            '<div class="chat-input"><input id="pv-input" placeholder="输入私聊消息..." onkeydown="if(event.key===\'Enter\')PrivMod.send()"><button id="pv-btn-send" onclick="PrivMod.send()">发送</button></div>';

        U.sys(document.getElementById('pv-msgs'), '提示：离线消息测试请先在线建立会话，再关闭对方窗口继续发送');

        if (!AppPage.appReady) {
            var b1 = document.getElementById('pv-btn-start'); if (b1) b1.disabled = true;
            var b2 = document.getElementById('pv-btn-send'); if (b2) b2.disabled = true;
            U.sys(document.getElementById('pv-msgs'), '后端认证未完成，暂不能操作');
        }

        for (var i = 0; i < this._msgs.length; i++) {
            this._renderMsg(this._msgs[i]);
        }
    },

    handleMsg: function(m) {
        var mt = m.msg_type;
        if (mt === 'private_conversation_created' && m.code === 200) {
            var newCid = m.content.conversation_id;
            if (newCid && this.cid && newCid !== this.cid) {
                this._msgs = [];
            }
            this.cid = newCid;
            State.privConv(this.cid);
            // Derive target from participants — safe when pv-target DOM absent
            var parts = (m.content && m.content.participants) || [];
            var fromMsg = parts.find(function(x) { return x !== State.user(); });
            var elT = document.getElementById('pv-target');
            this.target = fromMsg || (elT ? elT.value.trim() : State.target()) || '';
            State.target(this.target);
            var elL = document.getElementById('pv-label');
            if (elL && this.target) elL.textContent = '与 ' + this.target + ' 聊天中';
            this._pushSys('已建立与 ' + this.target + ' 的私聊');
            return;
        }
        if (mt === 'private_chat') {
            // CID isolation: skip if we have a cid and this message is for a different conversation
            if (this.cid && m.conversation_id && m.conversation_id !== this.cid) return;
            this._recoverState(m);
            this._msgs.push({ type: 'chat', m: m });
            this._renderMsg({ type: 'chat', m: m });
            return;
        }
        if (mt === 'error') {
            this._pushSys(m.err_msg || '');
            return;
        }
    },

    handleAck: function(msgId, status, rtt) {
        this._pushSys('ACK ' + status + (rtt ? ' rtt=' + rtt + 'ms' : ''));
    },

    _pushSys: function(text) {
        this._msgs.push({ type: 'sys', text: text });
        U.sys(document.getElementById('pv-msgs'), text);
    },

    _renderMsg: function(entry) {
        if (entry.type === 'sys') {
            U.sys(document.getElementById('pv-msgs'), entry.text);
        } else if (entry.type === 'chat') {
            var own = (entry.m.content && entry.m.content.from_user_id) === State.user();
            U.msg(document.getElementById('pv-msgs'), entry.m.content, own);
        }
    },

    startChat: function() {
        if (!AppPage.appReady) { U.sys(document.getElementById('pv-msgs'), '后端认证未完成，暂不能操作'); return; }
        var elT = document.getElementById('pv-target');
        var t = (elT ? elT.value.trim() : this.target) || '';
        if (t) this.cl.createPrivConv(t);
    },
    send: function() {
        if (!AppPage.appReady) { U.sys(document.getElementById('pv-msgs'), '后端认证未完成，暂不能操作'); return; }
        if (!this.cid) { U.sys(document.getElementById('pv-msgs'), '请先发起私聊会话'); return; }
        var t = document.getElementById('pv-input').value.trim();
        if (!t) return;
        this.cl.sendPrivMsg(this.cid, t, true);
        document.getElementById('pv-input').value = '';
    }
};
