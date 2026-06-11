// Room chat module — receives messages via AppPage dispatch
var RoomMod = {
    cl: null, room: null,

    render: function(area, client) {
        this.cl = client;
        this.room = State.room();
        area.innerHTML =
            '<div class="toolbar">' +
            '<input id="rm-room-name" placeholder="房间名称" style="width:120px">' +
            '<button onclick="RoomMod.create()">创建</button>' +
            '<input id="rm-room-id" placeholder="房间 ID" style="width:180px">' +
            '<button onclick="RoomMod.join()">加入</button>' +
            '<span class="room-id" id="rm-label">' + (this.room ? 'Room: ' + this.room.slice(0, 12) : '') + '</span>' +
            '</div>' +
            '<div class="chat-msgs" id="rm-msgs"></div>' +
            '<div class="chat-input"><input id="rm-input" placeholder="输入消息..." onkeydown="if(event.key===\'Enter\')RoomMod.send()"><button onclick="RoomMod.send()">发送</button></div>';
    },

    handleMsg: function(m) {
        var mt = m.msg_type;
        if (mt === 'room_created' && m.code === 200) {
            this.room = m.content.conversation_id;
            State.room(this.room);
            var el = document.getElementById('rm-label');
            if (el) el.textContent = 'Room: ' + this.room.slice(0, 12);
            U.sys(document.getElementById('rm-msgs'), '房间已创建: ' + this.room);
        }
        if (mt === 'room_joined' && m.code === 200) {
            this.room = m.content.conversation_id;
            State.room(this.room);
            var el = document.getElementById('rm-label');
            if (el) el.textContent = 'Room: ' + this.room.slice(0, 12);
            U.sys(document.getElementById('rm-msgs'), '已加入: ' + this.room);
        }
        if (mt === 'room_chat') {
            var own = (m.content && m.content.from_user_id) === State.user();
            U.msg(document.getElementById('rm-msgs'), m.content, own);
        }
        if (mt === 'error') {
            U.sys(document.getElementById('rm-msgs'), m.err_msg || '');
        }
    },

    handleAck: function(msgId, status, rtt) {
        U.sys(document.getElementById('rm-msgs'), 'ACK ' + status + (rtt ? ' rtt=' + rtt + 'ms' : ''));
    },

    create: function() {
        if (!AppPage.appReady) return;
        var name = document.getElementById('rm-room-name').value.trim() || 'Room';
        if (name) this.cl.createRoom(name);
    },
    join: function() {
        if (!AppPage.appReady) return;
        var rid = document.getElementById('rm-room-id').value.trim();
        if (rid) this.cl.joinRoom(rid);
    },
    send: function() {
        if (!AppPage.appReady || !this.room) return;
        var t = document.getElementById('rm-input').value.trim();
        if (!t) return;
        this.cl.sendRoomMsg(this.room, t, true);
        document.getElementById('rm-input').value = '';
    }
};
