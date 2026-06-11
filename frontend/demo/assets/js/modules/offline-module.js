// Offline module — removed from nav, kept as minimal stub
// Offline messages are delivered naturally through the private chat flow:
//   user002 closes window → user001 sends private_chat
//   → backend caches offline → user002 reconnects and receives
var OffMod = {
    render: function(area, client) {
        area.innerHTML = '<div class="dash"><p class="note">离线消息功能已整合到私聊模块。<br><br>真实流程：第二窗口关闭 → 对方发私聊 → 后端缓存 → 重新登录后自动补发。</p></div>';
    }
};
