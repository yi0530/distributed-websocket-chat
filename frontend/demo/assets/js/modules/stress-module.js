// Stress test dashboard module
var StressMod = {
    render: function(area) {
        area.innerHTML =
            '<div class="dash">' +
            '<h2>WebSocket idle 1000</h2>' +
            '<table><tr><th>指标</th><th>值</th></tr>' +
            '<tr><td>连接成功</td><td class="hi">1000 / 1000</td></tr>' +
            '<tr><td>登录成功</td><td class="hi">1000 / 1000</td></tr>' +
            '<tr><td>错误率</td><td class="hi">0.0%</td></tr>' +
            '<tr><td>平均连接耗时</td><td>28.1 ms</td></tr>' +
            '<tr><td>RSS 峰值</td><td class="hi">42.39 MB</td></tr></table>' +
            '<h2>Long Polling 1000</h2>' +
            '<table><tr><th>指标</th><th>值</th></tr>' +
            '<tr><td>总轮询</td><td class="hi">6000 / 6000</td></tr>' +
            '<tr><td>错误率</td><td class="hi">0.0%</td></tr>' +
            '<tr><td>RSS 峰值</td><td class="hi">28.31 MB</td></tr>' +
            '<tr><td>平均延迟</td><td>5131 ms</td></tr></table>' +
            '<h2>WebSocket vs Long Polling 对比</h2>' +
            '<table><tr><th>指标</th><th>WS 1000</th><th>LP 1000</th></tr>' +
            '<tr><td>成功率</td><td class="hi">100%</td><td class="hi">100%</td></tr>' +
            '<tr><td>RSS 峰值</td><td>42.39 MB</td><td>28.31 MB</td></tr>' +
            '<tr><td>平均延迟</td><td>28.1 ms</td><td>5131 ms</td></tr></table>' +
            '<p class="note">数据来自 tools/load_test/ CLI 压测，浏览器仅展示结果。</p></div>';
    }
};
