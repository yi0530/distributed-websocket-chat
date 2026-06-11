// Room chat module — messages cached and routed by msg_type
var RoomMod = {
    cl: null, room: null, _msgs: [],

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

        // Disable buttons if not ready
        if (!AppPage.appReady) {
            var bc = document.getElementById('rm-btn-create'); if (bc) bc.disabled = true;
            var bj = document.getElementById('rm-btn-join'); if (bj) bj.disabled = true;
            var bs = document.getElementById('rm-btn-send'); if (bs) bs.disabled = true;
            U.sys(document.getElementById('rm-msgs'), '后端认证未完成，暂不能操作');
        }

        // Replay cached messages
        for (var i = 0; i < this._msgs.length; i++) {
            this._renderMsg(this._msgs[i]);
        }
    },

    handleMsg: function(m) {
        var mt = m.msg_type;
        if (mt === 'room_created' && m.code === 200) {
            var newRoom = m.content.conversation_id;
            if (newRoom && this.room && newRoom !== this.room) {
                this._msgs = [];
            }
            this.room = newRoom;
            State.room(this.room);
            var el = document.getElementById('rm-label');
            if (el) el.textContent = 'Room: ' + this.room.slice(0, 12);
            this._pushSys('房间已创建: ' + this.room);
            return;
        }
        if (mt === 'room_joined' && m.code === 200) {
            var newRoom = m.content.conversation_id;
            if (newRoom && this.room && newRoom !== this.room) {
                this._msgs = [];
            }
            this.room = newRoom;
            State.room(this.room);
            var el = document.getElementById('rm-label');
            if (el) el.textContent = 'Room: ' + this.room.slice(0, 12);
            this._pushSys('已加入: ' + this.room);
            return;
        }
        if (mt === 'room_chat') {
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
        if (!this.room) return;
        var t = document.getElementById('rm-input').value.trim();
        if (!t) return;
        this.cl.sendRoomMsg(this.room, t, true);
        document.getElementById('rm-input').value = '';
    }
};
