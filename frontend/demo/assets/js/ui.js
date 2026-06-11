// UI helpers
var U = {
    esc: function(s) { if (!s) return ''; return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); },
    msg: function(el, content, own, extra) {
        var d = document.createElement('div'); d.className = 'msg ' + (own ? 'msg-own' : 'msg-other');
        var from = content.from_user_id || content.from || '';
        var txt = content.text || '';
        var html = '<span class="msg-sender">' + U.esc(from) + '</span><div class="msg-text">' + U.esc(txt) + '</div>';
        if (extra && extra.offline) html += '<span class="msg-offline">[离线补发]</span>';
        if (extra && extra.ack) { var a = extra.ack; html += '<span class="msg-ack ack-' + a + '">' + a + '</span>'; }
        d.innerHTML = html; el.appendChild(d); el.scrollTop = el.scrollHeight;
    },
    sys: function(el, text) {
        var d = document.createElement('div'); d.className = 'msg-sys'; d.textContent = text;
        el.appendChild(d); el.scrollTop = el.scrollHeight;
    },
    proto: function(el, e) {
        var r = document.createElement('div'); r.className = 'pr pr-' + e.dir.toLowerCase();
        var sym = { SEND:'↑', RECV:'↓', SYSTEM:'●', ERROR:'⚠' }[e.dir]||'?';
        r.innerHTML = '<span class="pr-time">'+e.time+'</span> <span class="pr-dir">'+sym+' '+e.dir+'</span> <span class="pr-type">'+e.type+'</span> <span class="pr-sum">'+U.esc(e.summary)+'</span>';
        if (e.raw) { r.style.cursor='pointer'; r.title='Click to see raw JSON'; r.onclick = function() {
            var x = r.querySelector('.pr-raw'); if (x) { x.remove(); return; }
            x = document.createElement('div'); x.className = 'pr-raw'; x.textContent = JSON.stringify(e.raw,null,2); r.appendChild(x);
        };}
        el.appendChild(r); el.scrollTop = el.scrollHeight;
    },
    conn: function(el, ok) { el.textContent = ok ? '● 已连接' : '○ 未连接'; el.className = 'top-conn ' + (ok?'top-ok':'top-off'); },
    badge: function(el, u) { el.textContent = u || 'Not logged in'; },
    tok: function(el, t) { el.textContent = t ? 'Token: ' + t.slice(0,16) + '...' : 'No token'; },
    clear: function(el) { el.innerHTML = ''; },
    err: function(el, msg) { var d = document.createElement('div'); d.className='err-msg'; d.textContent=msg; el.prepend(d); setTimeout(function(){d.remove();},4000); },
};
