// Private chat module — messages cached, state recovered, CID-isolated, conversation list
var PrivMod = {
    cl: null, cid: null, target: null, _msgs: [], _convs: [],

    _recoverState: function(m) {
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
        var elT = document.getElementById('pv-target');
        if (elT && this.target) elT.value = this.target;
        var elL = document.getElementById('pv-label');
        if (elL && this.target) elL.textContent = '与 ' + this.target + ' 聊天中';
    },

    render: function(area, client) {
        this.cl = client;
        this.cid = State.privConv();
        this.target = State.target();
        var self = this;
        area.innerHTML =
            '<div class="toolbar">' +
            '<input id="pv-target" placeholder="目标用户" value="' + (this.target || 'user002') + '" style="width:120px">' +
            '<button id="pv-btn-start" onclick="PrivMod.startChat()">发起私聊</button>' +
            '<span class="hint" id="pv-label">' + (this.target ? '与 ' + this.target + ' 聊天中' : '') + '</span>' +
            '</div>' +
            '<div style="padding:8px 16px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px;font-size:13px;color:var(--text-secondary);flex-shrink:0">' +
            '历史私聊 <button id="pv-btn-refresh" onclick="PrivMod.refreshList()" style="padding:4px 10px;border:1px solid var(--border-light);border-radius:4px;background:var(--bg-surface);color:var(--text-secondary);cursor:pointer;font-size:11px">刷新</button>' +
            '</div>' +
            '<div id="pv-list" style="max-height:120px;overflow-y:auto;flex-shrink:0;font-size:13px"></div>' +
            '<div class="chat-msgs" id="pv-msgs" style="border-top:1px solid var(--border)"></div>' +
            '<div class="chat-input"><input id="pv-input" placeholder="输入私聊消息..." onkeydown="if(event.key===\'Enter\')PrivMod.send()"><button id="pv-btn-send" onclick="PrivMod.send()">发送</button></div>';

        this._renderConvList();
        U.sys(document.getElementById('pv-msgs'), '提示：离线消息测试请先在线建立会话，再关闭对方窗口继续发送');

        if (!AppPage.appReady) {
            var b1 = document.getElementById('pv-btn-start'); if (b1) b1.disabled = true;
            var b2 = document.getElementById('pv-btn-send'); if (b2) b2.disabled = true;
            var br = document.getElementById('pv-btn-refresh'); if (br) br.disabled = true;
            U.sys(document.getElementById('pv-msgs'), '后端认证未完成，暂不能操作');
        }

        for (var i = 0; i < this._msgs.length; i++) {
            this._renderMsg(this._msgs[i]);
        }

        if (AppPage.appReady && this.cl) this.cl.listMyConversations();
    },

    _renderConvList: function() {
        var el = document.getElementById('pv-list');
        if (!el) return;
        var privConvs = [];
        for (var i = 0; i < this._convs.length; i++) {
            if (this._convs[i].type === 'private') privConvs.push(this._convs[i]);
        }
        if (privConvs.length === 0) {
            el.innerHTML = '<div style="padding:8px 16px;color:var(--text-tertiary);font-size:12px">暂无历史私聊</div>';
            return;
        }
        var html = '';
        for (var i = 0; i < privConvs.length; i++) {
            var c = privConvs[i];
            var peer = c.peer || 'unknown';
            html += '<div style="padding:6px 16px;display:flex;align-items:center;gap:8px;border-bottom:1px solid rgba(255,255,255,0.03)">' +
                '<span style="flex:1;color:var(--text)">' + U.esc(peer) + '</span>' +
                '<button onclick="PrivMod.enterChat(\'' + c.conversation_id + '\',\'' + U.esc(peer) + '\')" style="padding:3px 10px;border:1px solid var(--border-light);border-radius:4px;background:var(--bg-surface);color:var(--accent);cursor:pointer;font-size:11px">进入聊天</button>' +
                '</div>';
        }
        el.innerHTML = html;
    },

    enterChat: function(cid, peer) {
        this.cid = cid;
        State.privConv(cid);
        this.target = peer;
        State.target(peer);
        var elT = document.getElementById('pv-target');
        if (elT) elT.value = peer;
        var elL = document.getElementById('pv-label');
        if (elL) elL.textContent = '与 ' + peer + ' 聊天中';
        this._pushSys('已进入与 ' + peer + ' 的私聊');
    },

    refreshList: function() {
        if (!AppPage.appReady || !this.cl) return;
        this.cl.listMyConversations();
    },

    handleMsg: function(m) {
        var mt = m.msg_type;
        if (mt === 'my_conversations' && m.code === 200) {
            this._convs = (m.content && m.content.conversations) || [];
            this._renderConvList();
            return;
        }
        if (mt === 'private_conversation_created' && m.code === 200) {
            var newCid = m.content.conversation_id;
            if (newCid && this.cid && newCid !== this.cid) {
                this._msgs = [];
            }
            this.cid = newCid;
            State.privConv(this.cid);
            var parts = (m.content && m.content.participants) || [];
            var fromMsg = parts.find(function(x) { return x !== State.user(); });
            var elT = document.getElementById('pv-target');
            this.target = fromMsg || (elT ? elT.value.trim() : State.target()) || '';
            State.target(this.target);
            var elL = document.getElementById('pv-label');
            if (elL && this.target) elL.textContent = '与 ' + this.target + ' 聊天中';
            this._pushSys('已建立与 ' + this.target + ' 的私聊');
            if (this.cl) this.cl.listMyConversations();
            return;
        }
        if (mt === 'private_chat') {
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
