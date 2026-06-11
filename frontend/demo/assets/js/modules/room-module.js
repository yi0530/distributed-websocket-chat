// Room chat module
var RoomMod = {
    cl: null, room: null,

    render: function(area, client) {
        this.cl = client; this.room = State.room();
        var self = this;
        area.innerHTML =
            '<div class="toolbar">' +
            '<input id="rm-room-name" placeholder="Room name" style="width:120px">' +
            '<button onclick="RoomMod.create()">Create</button>' +
            '<input id="rm-room-id" placeholder="Room ID" style="width:180px">' +
            '<button onclick="RoomMod.join()">Join</button>' +
            '<span class="room-id" id="rm-label">' + (this.room ? 'Room: ' + this.room.slice(0, 12) : '') + '</span>' +
            '</div>' +
            '<div class="chat-msgs" id="rm-msgs"></div>' +
            '<div class="chat-input"><input id="rm-input" placeholder="Message..."><button onclick="RoomMod.send()">Send</button></div>';
        var ocb = this.cl.onMsg;
        this.cl.onMsg = function(m) {
            if (ocb) ocb(m);
            var mt = m.msg_type;
            if (mt === 'room_created' && m.code === 200) {
                self.room = m.content.conversation_id; State.room(self.room);
                document.getElementById('rm-label').textContent = 'Room: ' + self.room.slice(0, 12);
                U.sys(document.getElementById('rm-msgs'), 'Room: ' + self.room);
            }
            if (mt === 'room_joined' && m.code === 200) {
                self.room = m.content.conversation_id; State.room(self.room);
                document.getElementById('rm-label').textContent = 'Room: ' + self.room.slice(0, 12);
                U.sys(document.getElementById('rm-msgs'), 'Joined: ' + self.room);
            }
            if (mt === 'room_chat') {
                var own = (m.content && m.content.from_user_id) === State.user();
                U.msg(document.getElementById('rm-msgs'), m.content, own);
            }
        };
        var oca = this.cl.onAck;
        this.cl.onAck = function(id, st, rtt) {
            if (oca) oca(id, st, rtt);
            U.sys(document.getElementById('rm-msgs'), 'ACK ' + st + (rtt ? ' rtt=' + rtt + 'ms' : ''));
        };
    },

    create: function() {
        var self = this;
        this.cl.createRoom(document.getElementById('rm-room-name').value.trim() || 'Room');
    },
    join: function() {
        var self = this;
        this.cl.joinRoom(document.getElementById('rm-room-id').value.trim());
    },
    send: function() {
        if (!this.room) return;
        var t = document.getElementById('rm-input').value.trim(); if (!t) return;
        this.cl.sendRoomMsg(this.room, t, true);
        document.getElementById('rm-input').value = '';
    }
};
