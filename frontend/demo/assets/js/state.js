// Per-tab session state (sessionStorage)
const State = {
    _k: function(key) { return 'demo_' + key; },
    get: function(k) { try { return sessionStorage.getItem(this._k(k)); } catch(e) { return null; } },
    set: function(k, v) { try { sessionStorage.setItem(this._k(k), v); } catch(e) {} },
    del: function(k) { try { sessionStorage.removeItem(this._k(k)); } catch(e) {} },

    user: function(v) { return arguments.length ? this.set('user',v) : this.get('user'); },
    token: function(v) { return arguments.length ? this.set('token',v) : this.get('token'); },
    room: function(v) { return arguments.length ? this.set('room',v) : this.get('room'); },
    privConv: function(v) { return arguments.length ? this.set('privConv',v) : this.get('privConv'); },
    target: function(v) { return arguments.length ? this.set('target',v) : this.get('target'); },

    loggedIn: function() { return !!(this.user() && this.token()); },

    logout: function() {
        if (window.__client) { window.__client.close(); window.__client = null; }
        var keys = ['user','token','room','privConv','target'];
        for (var i=0;i<keys.length;i++) this.del(keys[i]);
    }
};
