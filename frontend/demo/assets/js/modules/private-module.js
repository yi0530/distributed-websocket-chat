// Private chat module — messages cached, state recovered, CID-isolated, conversation list
var PrivMod = {
    cl: null, cid: null, target: null, _msgs: [], _convs: [], _typingUsers: {}, _typingTimer: null,

    _recoverState: function(m) {
        var msgCid = m.content && m.content.conversation_id;
        if (!this.cid && msgCid) {
            this.cid = msgCid;
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
            '<div class="chat-msgs" id="pv-msgs"></div>' +
            '<div id="pv-typing" style="height:20px;padding:0 16px;font-size:12px;color:#6b7280;font-style:italic"></div>' +
            '<div class="chat-input"><input id="pv-input" placeholder="输入私聊消息..." onkeydown="if(event.key===\'Enter\')PrivMod.send()" oninput="PrivMod._onTyping()"><button id="pv-btn-send" onclick="PrivMod.send()">发送</button></div>';

        U.sys(document.getElementById('pv-msgs'), '提示：离线消息测试请先在线建立会话，再关闭对方窗口继续发送');

        this._loadMsgs();

        if (!AppPage.appReady) {
            var b1 = document.getElementById('pv-btn-start'); if (b1) b1.disabled = true;
            var b2 = document.getElementById('pv-btn-send'); if (b2) b2.disabled = true;
            U.sys(document.getElementById('pv-msgs'), '后端认证未完成，暂不能操作');
        }

        for (var i = 0; i < this._msgs.length; i++) {
            this._renderMsg(this._msgs[i]);
        }

        if (AppPage.appReady && this.cl) {
            this.cl.listMyConversations();
            if (this.cid) this.cl.getChatHistory(this.cid);
        }
    },

    renderList: function(el) {
        var html = '<div style="padding:6px 8px;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:0.5px">历史私聊</div>';
        var privConvs = [];
        for (var i = 0; i < this._convs.length; i++) {
            if (this._convs[i].type === 'private') privConvs.push(this._convs[i]);
        }
        if (privConvs.length === 0) {
            html += '<div style="padding:8px;color:#6b7280;font-size:12px">暂无历史私聊</div>';
        } else {
            for (var i = 0; i < privConvs.length; i++) {
                var c = privConvs[i];
                var peer = c.peer || 'unknown';
                var isCurrent = (this.cid === c.conversation_id);
                html += '<div style="padding:8px;margin:2px 0;border-radius:6px;cursor:pointer;' +
                    (isCurrent ? 'background:rgba(37,99,235,0.12);color:#2563eb;' : 'color:var(--text);') + '"' +
                    (isCurrent ? '' : ' onclick="PrivMod.enterChat(\'' + c.conversation_id + '\',\'' + U.esc(peer) + '\')"') + '>' +
                    '<div style="font-weight:600;font-size:13px">' + U.esc(peer) + '</div>' +
                    (isCurrent ? '<div style="font-size:11px;color:var(--muted)">当前聊天</div>' : '<div style="font-size:11px;color:var(--muted)">点击进入聊天</div>') +
                    '</div>';
            }
        }
        html += '<button onclick="PrivMod.refreshList()" style="margin-top:8px;padding:4px;width:100%;border:1px solid var(--border);border-radius:6px;background:transparent;color:var(--muted);cursor:pointer;font-size:11px">刷新</button>';
        el.innerHTML = html;
    },

    enterChat: function(cid, peer) {
        if (this.cid !== cid) {
            this._msgs = [];
            var elM = document.getElementById('pv-msgs'); if (elM) elM.innerHTML = '';
        }
        this.cid = cid;
        State.privConv(cid);
        this.target = peer;
        State.target(peer);
        this._loadMsgs();
        var elT = document.getElementById('pv-target');
        if (elT) elT.value = peer;
        var elL = document.getElementById('pv-label');
        if (elL) elL.textContent = '与 ' + peer + ' 聊天中';
        for (var i = 0; i < this._msgs.length; i++) {
            this._renderMsg(this._msgs[i]);
        }
        this._pushSys('已进入与 ' + peer + ' 的私聊');
        if (this.cl) this.cl.getChatHistory(cid);
        if (AppPage && AppPage.renderSidebar) AppPage.renderSidebar();
    },

    refreshList: function() {
        if (!AppPage.appReady || !this.cl) return;
        this.cl.listMyConversations();
    },

    handleMsg: function(m) {
        var mt = m.msg_type;
        if (mt === 'my_conversations' && m.code === 200) {
            this._convs = (m.content && m.content.conversations) || [];
            return;
        }
        if (mt === 'private_conversation_created' && m.code === 200) {
            var newCid = m.content.conversation_id;
            if (newCid && this.cid !== newCid) {
                this._msgs = [];
                var elM = document.getElementById('pv-msgs'); if (elM) elM.innerHTML = '';
            }
            this.cid = newCid;
            State.privConv(this.cid);
            var parts = (m.content && m.content.participants) || [];
            var fromMsg = parts.find(function(x) { return x !== State.user(); });
            var elT = document.getElementById('pv-target');
            this.target = fromMsg || (elT ? elT.value.trim() : State.target()) || '';
            State.target(this.target);
            this._loadMsgs();
            for (var i2 = 0; i2 < this._msgs.length; i2++) {
                this._renderMsg(this._msgs[i2]);
            }
            var elL = document.getElementById('pv-label');
            if (elL && this.target) elL.textContent = '与 ' + this.target + ' 聊天中';
            this._pushSys('已建立与 ' + this.target + ' 的私聊');
            if (this.cl) { this.cl.listMyConversations(); this.cl.getChatHistory(this.cid); }
            return;
        }
        if (mt === 'chat_history' && m.code === 200) {
            var histCidP = m.content && m.content.conversation_id;
            if (this.cid && histCidP && histCidP !== this.cid) return;
            var histMsgsP = (m.content && m.content.messages) || [];
            this._msgs = [];
            var histElP = document.getElementById('pv-msgs');
            if (histElP) histElP.innerHTML = '';
            for (var hp = 0; hp < histMsgsP.length; hp++) {
                var hmp = histMsgsP[hp];
                var entryP = { type: 'chat', m: { msg_type: hmp.msg_type, content: { conversation_id: hmp.conversation_id, from_user_id: hmp.from_user_id, text: hmp.text } } };
                this._msgs.push(entryP);
                this._renderMsg(entryP);
            }
            this._saveMsgs(histCidP);
            setTimeout(function(self) { self._sendReadReceipt(); }, 200, this);
            return;
        }
        if (mt === 'private_chat') {
            var msgCid2 = m.content && m.content.conversation_id;
            if (this.cid && msgCid2 && msgCid2 !== this.cid) return;
            this._recoverState(m);
            this._msgs.push({ type: 'chat', m: m });
            this._renderMsg({ type: 'chat', m: m });
            this._saveMsgs(m.content && m.content.conversation_id);
            this._sendReadReceipt();
            return;
        }
        if (mt === 'user_typing') {
            var tuid = m.content && m.content.user_id;
            var tcid = m.content && m.content.conversation_id;
            if (!tuid || (this.cid && tcid && tcid !== this.cid)) return;
            if (m.content.typing) {
                this._typingUsers[tuid] = Date.now();
            } else {
                delete this._typingUsers[tuid];
            }
            this._showTyping();
            return;
        }
        if (mt === 'read_receipt') {
            var rruid = m.content && m.content.user_id;
            var rrcid = m.content && m.content.conversation_id;
            if (!rruid || (this.cid && rrcid && rrcid !== this.cid)) return;
            this._pushSys(rruid + ' 已读');
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
        this._saveMsgs();
    },

    _saveMsgs: function(fallbackKey) {
        var key = this.cid || fallbackKey;
        if (!key) return;
        try { sessionStorage.setItem('demo_msgs_priv_' + key, JSON.stringify(this._msgs.slice(-100))); } catch(e) {}
    },

    _loadMsgs: function() {
        if (!this.cid) return;
        if (this._msgs.length > 0) return;
        try {
            var raw = sessionStorage.getItem('demo_msgs_priv_' + this.cid);
            if (raw) { this._msgs = JSON.parse(raw); }
        } catch(e) { this._msgs = []; }
    },

    _renderMsg: function(entry) {
        if (entry.type === 'sys') {
            U.sys(document.getElementById('pv-msgs'), entry.text);
        } else if (entry.type === 'chat') {
            var own = (entry.m.content && entry.m.content.from_user_id) === State.user();
            U.msg(document.getElementById('pv-msgs'), entry.m.content, own);
        }
    },

    _onTyping: function() {
        if (!this.cid || !this.cl) return;
        this.cl.sendTypingStart(this.cid);
        clearTimeout(this._typingTimer);
        this._typingTimer = setTimeout(function(self) {
            if (self.cid && self.cl) self.cl.sendTypingStop(self.cid);
        }, 2000, this);
    },

    _showTyping: function() {
        var el = document.getElementById('pv-typing');
        if (!el) return;
        var now = Date.now();
        var names = [];
        for (var uid in this._typingUsers) {
            if (now - this._typingUsers[uid] < 5000) {
                names.push(uid);
            } else {
                delete this._typingUsers[uid];
            }
        }
        el.textContent = names.length > 0 ? names.join(', ') + ' 正在输入...' : '';
    },

    _sendReadReceipt: function() {
        if (!this.cid || !this.cl || this._msgs.length === 0) return;
        var last = this._msgs[this._msgs.length - 1];
        var lastMid = (last.m && last.m.msg_id) || '';
        if (lastMid) this.cl.sendReadReceipt(this.cid, lastMid);
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
