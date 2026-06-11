// JSON application protocol builder
const Proto = {
    genMsgId: function(p) { return (p||'m') + '-' + Date.now() + '-' + Math.random().toString(36).slice(2,8); },
    base: function(type, id, extra) {
        var m = { version: String(DemoConfig.APP_VERSION), msg_type: type, msg_id: id, code: 200, content: null, err_msg: '', timestamp: Math.floor(Date.now()/1000) };
        if (extra) Object.assign(m, extra);
        return m;
    },
    register: function(user, pass) {
        return this.base('register', this.genMsgId('reg'), { from: user, content: { password: pass } });
    },
    login: function(user, pass) {
        return this.base('login', this.genMsgId('login'), { from: user, content: pass });
    },
    createRoom: function(name) {
        return this.base('create_room', this.genMsgId('cr'), { name: name });
    },
    joinRoom: function(rid) {
        return this.base('join_room', this.genMsgId('join'), { conversation_id: rid });
    },
    roomChat: function(rid, text, ack) {
        return this.base('room_chat', this.genMsgId('chat'), { conversation_id: rid, payload: { text: text }, need_ack: ack !== false });
    },
    createPrivConv: function(target) {
        return this.base('create_private_conversation', this.genMsgId('cpc'), { target_user_id: target });
    },
    privateChat: function(cid, text, ack) {
        return this.base('private_chat', this.genMsgId('priv'), { conversation_id: cid, payload: { text: text }, need_ack: ack !== false });
    },
    listRooms: function() {
        return this.base('list_rooms', this.genMsgId('lr'));
    },
    listMyConversations: function() {
        return this.base('list_my_conversations', this.genMsgId('lmc'));
    },
    getChatHistory: function(cid) {
        return this.base('get_chat_history', this.genMsgId('hist'), { conversation_id: cid });
    },
};
