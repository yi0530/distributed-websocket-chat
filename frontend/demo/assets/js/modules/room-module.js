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
            '</div>' +
            '<div style="padding:8px 16px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px;font-size:13px;color:var(--text-secondary);flex-shrink:0">' +
            '已有群聊 <button id="rm-btn-refresh" onclick="RoomMod.refreshList()" style="padding:4px 10px;border:1px solid var(--border-light);border-radius:4px;background:var(--bg-surface);color:var(--text-secondary);cursor:pointer;font-size:11px">刷新</button>' +
            '</div>' +
            '<div id="rm-list" style="max-height:150px;overflow-y:auto;flex-shrink:0;font-size:13px"></div>' +
            '<div class="chat-msgs" id="rm-msgs" style="border-top:1px solid var(--border)"></div>' +
            '<div class="chat-input"><input id="rm-input" placeholder="输入消息..." onkeydown="if(event.key===\'Enter\')RoomMod.send()"><button id="rm-btn-send" onclick="RoomMod.send()">发送</button></div>';

        this._renderRoomList();

        if (!AppPage.appReady) {
            var bc = document.getElementById('rm-btn-create'); if (bc) bc.disabled = true;
            var bj = document.getElementById('rm-btn-join'); if (bj) bj.disabled = true;
            var bs = document.getElementById('rm-btn-send'); if (bs) bs.disabled = true;
            var br = document.getElementById('rm-btn-refresh'); if (br) br.disabled = true;
            U.sys(document.getElementById('rm-msgs'), '后端认证未完成，暂不能操作');
        }

        for (var i = 0; i < this._msgs.length; i++) {
            this._renderMsg(this._msgs[i]);
        }

        // Auto-refresh list on first render
        if (AppPage.appReady && this.cl) this.cl.listRooms();
    },

    _renderRoomList: function() {
        var el = document.getElementById('rm-list');
        if (!el) return;
        if (this._rooms.length === 0) {
            el.innerHTML = '<div style="padding:8px 16px;color:var(--text-tertiary);font-size:12px">暂无群聊，创建一个吧</div>';
            return;
        }
        var html = '';
        for (var i = 0; i < this._rooms.length; i++) {
            var r = this._rooms[i];
            html += '<div style="padding:6px 16px;display:flex;align-items:center;gap:8px;border-bottom:1px solid rgba(255,255,255,0.03)">' +
                '<span style="flex:1;color:var(--text)">' + U.esc(r.name || r.conversation_id) + '</span>' +
                '<span style="color:var(--text-tertiary);font-size:11px">' + (r.participant_count || 0) + '人</span>' +
                '<button onclick="RoomMod.joinById(\'' + r.conversation_id + '\')" style="padding:3px 10px;border:1px solid var(--border-light);border-radius:4px;background:var(--bg-surface);color:var(--accent);cursor:pointer;font-size:11px">加入</button>' +
                '</div>';
        }
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
            this._renderRoomList();
            return;
        }
        if (mt === 'room_created' && m.code === 200) {
            var newRoom = m.content.conversation_id;
            if (newRoom && this.room && newRoom !== this.room) {
                this._msgs = [];
            }
            this.room = newRoom;
            State.room(this.room);
            U.sys(document.getElementById('rm-msgs'), '房间已创建: ' + this.room);
            // Refresh room list
            if (this.cl) this.cl.listRooms();
            return;
        }
        if (mt === 'room_joined' && m.code === 200) {
            var newRoom = m.content.conversation_id;
            if (newRoom && this.room && newRoom !== this.room) {
                this._msgs = [];
            }
            this.room = newRoom;
            State.room(this.room);
            U.sys(document.getElementById('rm-msgs'), '已加入: ' + this.room);
            if (this.cl) this.cl.listRooms();
            return;
        }
        if (mt === 'room_chat') {
            if (this.room && m.conversation_id && m.conversation_id !== this.room) return;
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
        U.sys(document.getElementById('rm-msgs'), text);
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
