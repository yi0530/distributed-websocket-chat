// Room chat module — messages cached, room-ID-isolated, room list
var RoomMod = {
    cl: null, room: null, _msgs: [], _rooms: [],

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
            '<div class="chat-input"><input id="rm-input" placeholder="输入消息..." onkeydown="if(event.key===\'Enter\')RoomMod.send()"><button id="rm-btn-send" onclick="RoomMod.send()">发送</button></div>';

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

        // Auto-refresh list on first render
        if (AppPage.appReady && this.cl) this.cl.listRooms();
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
            U.sys(document.getElementById('rm-msgs'), '房间已创建: ' + this.room);
            if (this.cl) this.cl.listRooms();
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
            U.sys(document.getElementById('rm-msgs'), '已加入: ' + this.room);
            if (this.cl) this.cl.listRooms();
            return;
        }
        if (mt === 'room_chat') {
            var msgCid = m.content && m.content.conversation_id;
            if (this.room && msgCid && msgCid !== this.room) return;
            this._msgs.push({ type: 'chat', m: m });
            this._renderMsg({ type: 'chat', m: m });
            this._saveMsgs(msgCid);
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
            if (raw) {
                sessionStorage.removeItem('demo_msgs_room_' + this.room);
                this._msgs = JSON.parse(raw);
                var el = document.getElementById('rm-msgs');
                if (el) el.innerHTML = '';
                for (var i = 0; i < this._msgs.length; i++) {
                    this._renderMsg(this._msgs[i]);
                }
            }
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
