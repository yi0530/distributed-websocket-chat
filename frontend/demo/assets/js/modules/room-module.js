// Room chat module — messages cached, room-ID-isolated, room list
var RoomMod = {
    cl: null, room: null, _msgs: [], _rooms: [], _typingUsers: {}, _typingTimer: null,

    render: function(area, client) {
        this.cl = client;
        this.room = State.room();
        var self = this;
        area.innerHTML =
            '<div class="toolbar">' +
            '<input id="rm-room-name" placeholder="房间名称" style="width:120px">' +
            '<button id="rm-btn-create" onclick="RoomMod.create()">创建</button>' +
            '<input id="rm-room-id" placeholder="房间 ID" style="width:180px">' +
            '<button id="rm-btn-join" onclick="RoomMod.join()">加入</button>' +
            '<span class="room-id" id="rm-label">' + (this.room ? 'Room: ' + this.room.slice(0, 12) : '') + '</span>' +
            '</div>' +
            '<div class="chat-msgs" id="rm-msgs"></div>' +
            '<div id="rm-typing" style="height:20px;padding:0 16px;font-size:12px;color:#6b7280;font-style:italic"></div>' +
            '<div class="chat-input"><input id="rm-input" placeholder="输入消息..." onkeydown="if(event.key===\'Enter\')RoomMod.send()" oninput="RoomMod._onTyping()"><button id="rm-btn-send" onclick="RoomMod.send()">发送</button></div>';

        this._loadMsgs();

        if (!AppPage.appReady) {
            var bc = document.getElementById('rm-btn-create'); if (bc) bc.disabled = true;
            var bj = document.getElementById('rm-btn-join'); if (bj) bj.disabled = true;
            var bs = document.getElementById('rm-btn-send'); if (bs) bs.disabled = true;
            U.sys(document.getElementById('rm-msgs'), '后端认证未完成，暂不能操作');
        }

        for (var i = 0; i < this._msgs.length; i++) {
            this._renderMsg(this._msgs[i]);
        }

        // Auto-refresh list and history on first render
        if (AppPage.appReady && this.cl) {
            this.cl.listRooms();
            if (this.room) this.cl.getChatHistory(this.room);
        }
    },

    renderList: function(el) {
        var html = '<div style="padding:6px 8px;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:0.5px">群聊房间</div>';
        if (this._rooms.length === 0) {
            html += '<div style="padding:8px;color:#6b7280;font-size:12px">暂无群聊</div>';
        } else {
            for (var i = 0; i < this._rooms.length; i++) {
                var r = this._rooms[i];
                var isJoined = (this.room === r.conversation_id);
                html += '<div style="padding:8px;margin:2px 0;border-radius:6px;cursor:pointer;' +
                    (isJoined ? 'background:rgba(37,99,235,0.12);color:#2563eb;' : 'color:var(--text);') + '"' +
                    (isJoined ? '' : ' onclick="RoomMod.joinById(\'' + r.conversation_id + '\')"') + '>' +
                    '<div style="font-weight:600;font-size:13px">' + U.esc(r.name || r.conversation_id.slice(0,8)) + '</div>' +
                    '<div style="font-size:11px;color:var(--muted)">' + (r.participant_count || 0) + '人' +
                    (isJoined ? ' · 已加入' : ' · 点击加入') + '</div>' +
                    '</div>';
            }
        }
        html += '<button onclick="RoomMod.refreshList()" style="margin-top:8px;padding:4px;width:100%;border:1px solid var(--border);border-radius:6px;background:transparent;color:var(--muted);cursor:pointer;font-size:11px">刷新</button>';
        el.innerHTML = html;
    },

    joinById: function(cid) {
        if (!AppPage.appReady) return;
        var el = document.getElementById('rm-room-id');
        if (el) el.value = cid;
        this.cl.joinRoom(cid);
    },

    refreshList: function() {
        if (!AppPage.appReady || !this.cl) return;
        this.cl.listRooms();
    },

    handleMsg: function(m) {
        var mt = m.msg_type;
        if (mt === 'room_list' && m.code === 200) {
            this._rooms = (m.content && m.content.rooms) || [];
            return;
        }
        if (mt === 'room_created' && m.code === 200) {
            var newRoom = m.content.conversation_id;
            if (newRoom && this.room !== newRoom) {
                this._msgs = [];
                var el = document.getElementById('rm-msgs'); if (el) el.innerHTML = '';
            }
            this.room = newRoom;
            State.room(this.room);
            var lbl = document.getElementById('rm-label');
            if (lbl) lbl.textContent = 'Room: ' + this.room.slice(0, 12);
            this._loadMsgs();
            for (var i3 = 0; i3 < this._msgs.length; i3++) { this._renderMsg(this._msgs[i3]); }
            U.sys(document.getElementById('rm-msgs'), '房间已创建: ' + this.room);
            if (this.cl) { this.cl.listRooms(); this.cl.getChatHistory(this.room); }
            return;
        }
        if (mt === 'room_joined' && m.code === 200) {
            var newRoom2 = m.content.conversation_id;
            if (newRoom2 && this.room !== newRoom2) {
                this._msgs = [];
                var el2 = document.getElementById('rm-msgs'); if (el2) el2.innerHTML = '';
            }
            this.room = newRoom2;
            State.room(this.room);
            var lbl = document.getElementById('rm-label');
            if (lbl) lbl.textContent = 'Room: ' + this.room.slice(0, 12);
            this._loadMsgs();
            for (var i4 = 0; i4 < this._msgs.length; i4++) { this._renderMsg(this._msgs[i4]); }
            U.sys(document.getElementById('rm-msgs'), '已加入: ' + this.room);
            if (this.cl) { this.cl.listRooms(); this.cl.getChatHistory(this.room); }
            return;
        }
        if (mt === 'chat_history' && m.code === 200) {
            var histCid = m.content && m.content.conversation_id;
            // Ignore if this history is for a different room than the one we're viewing
            if (this.room && histCid && histCid !== this.room) return;
            var histMsgs = (m.content && m.content.messages) || [];
            this._msgs = [];
            var histEl = document.getElementById('rm-msgs');
            if (histEl) histEl.innerHTML = '';
            for (var hi = 0; hi < histMsgs.length; hi++) {
                var hm = histMsgs[hi];
                var entry = { type: 'chat', m: { msg_type: hm.msg_type, content: { conversation_id: hm.conversation_id, from_user_id: hm.from_user_id, text: hm.text } } };
                this._msgs.push(entry);
                this._renderMsg(entry);
            }
            this._saveMsgs(histCid);
            setTimeout(function(self) { self._sendReadReceipt(); }, 200, this);
            return;
        }
        if (mt === 'room_chat') {
            var msgCid = m.content && m.content.conversation_id;
            if (this.room && msgCid && msgCid !== this.room) return;
            this._msgs.push({ type: 'chat', m: m });
            this._renderMsg({ type: 'chat', m: m });
            this._saveMsgs(msgCid);
            this._sendReadReceipt();
            return;
        }
        if (mt === 'user_typing') {
            var tuid = m.content && m.content.user_id;
            var tcid = m.content && m.content.conversation_id;
            if (!tuid || (this.room && tcid && tcid !== this.room)) return;
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
            if (!rruid || (this.room && rrcid && rrcid !== this.room)) return;
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
        U.sys(document.getElementById('rm-msgs'), text);
        this._saveMsgs();
    },

    _saveMsgs: function(fallbackKey) {
        var key = this.room || fallbackKey;
        if (!key) return;
        try { sessionStorage.setItem('demo_msgs_room_' + key, JSON.stringify(this._msgs.slice(-100))); } catch(e) {}
    },

    _loadMsgs: function() {
        if (!this.room) return;
        if (this._msgs.length > 0) return;
        try {
            var raw = sessionStorage.getItem('demo_msgs_room_' + this.room);
            if (raw) { this._msgs = JSON.parse(raw); }
        } catch(e) { this._msgs = []; }
    },

    _renderMsg: function(entry) {
        if (entry.type === 'sys') {
            U.sys(document.getElementById('rm-msgs'), entry.text);
        } else if (entry.type === 'chat') {
            var own = (entry.m.content && entry.m.content.from_user_id) === State.user();
            U.msg(document.getElementById('rm-msgs'), entry.m.content, own);
        }
    },

    _onTyping: function() {
        if (!this.room || !this.cl) return;
        this.cl.sendTypingStart(this.room);
        clearTimeout(this._typingTimer);
        this._typingTimer = setTimeout(function(self) {
            if (self.room && self.cl) self.cl.sendTypingStop(self.room);
        }, 2000, this);
    },

    _showTyping: function() {
        var el = document.getElementById('rm-typing');
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
        if (!this.room || !this.cl || this._msgs.length === 0) return;
        var last = this._msgs[this._msgs.length - 1];
        var lastMid = (last.m && last.m.msg_id) || '';
        if (lastMid) this.cl.sendReadReceipt(this.room, lastMid);
    },

    create: function() {
        if (!AppPage.appReady) { U.sys(document.getElementById('rm-msgs'), '后端认证未完成，暂不能操作'); return; }
        var name = document.getElementById('rm-room-name').value.trim() || 'Room';
        if (name) this.cl.createRoom(name);
    },
    join: function() {
        if (!AppPage.appReady) { U.sys(document.getElementById('rm-msgs'), '后端认证未完成，暂不能操作'); return; }
        var rid = document.getElementById('rm-room-id').value.trim();
        if (rid) this.cl.joinRoom(rid);
    },
    send: function() {
        if (!AppPage.appReady) { U.sys(document.getElementById('rm-msgs'), '后端认证未完成，暂不能操作'); return; }
        if (!this.room) { U.sys(document.getElementById('rm-msgs'), '请先创建或加入房间'); return; }
        var t = document.getElementById('rm-input').value.trim();
        if (!t) return;
        this.cl.sendRoomMsg(this.room, t, true);
        document.getElementById('rm-input').value = '';
    }
};
