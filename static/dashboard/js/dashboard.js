(() => {
    "use strict";

    const MAX_POINTS = 60;
    const state = {
        times: [], cpu: [], memory: [], netIn: [], reconnectTimer: null,
        latestMetric: null, lastBand: null, lastAdviceAt: 0,
        processTab: "cpu", processes: { cpu: [], memory: [] },
        socket: null, wsVersion: 0, serverId: "", servers: []
    };
    const byId = (id) => document.getElementById(id);
    const chart = echarts.init(byId("metricsChart"));

    chart.setOption({
        animationDurationUpdate: 280,
        grid: { top: 38, right: 48, bottom: 32, left: 42 },
        tooltip: { trigger: "axis", backgroundColor: "#122724", borderColor: "rgba(163,211,192,.2)", textStyle: { color: "#ecf7f2" } },
        legend: { top: 3, right: 0, textStyle: { color: "#8ca59d" }, data: ["CPU", "内存", "下载"] },
        xAxis: { type: "category", boundaryGap: false, data: [], axisLine: { lineStyle: { color: "rgba(163,211,192,.14)" } }, axisLabel: { color: "#718b83", formatter: (value) => value.slice(11) } },
        yAxis: [
            { type: "value", min: 0, max: 100, axisLabel: { color: "#718b83", formatter: "{value}%" }, splitLine: { lineStyle: { color: "rgba(163,211,192,.08)" } } },
            { type: "value", min: 0, axisLabel: { color: "#718b83", formatter: "{value}K" }, splitLine: { show: false } }
        ],
        series: [
            { name: "CPU", type: "line", data: [], smooth: .35, showSymbol: false, lineStyle: { width: 2, color: "#55e6a5" }, areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: "rgba(85,230,165,.24)" }, { offset: 1, color: "rgba(85,230,165,0)" }]) } },
            { name: "内存", type: "line", data: [], smooth: .35, showSymbol: false, lineStyle: { width: 2, color: "#58cce7" } },
            { name: "下载", type: "line", yAxisIndex: 1, data: [], smooth: .3, showSymbol: false, lineStyle: { width: 1.5, color: "#a68cff" } }
        ]
    });

    function bytesToGiB(value) { return ((value || 0) / 1024 ** 3).toFixed(1); }
    function formatRate(value) {
        const bytes = value || 0;
        if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB/s`;
        if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB/s`;
        return `${Math.round(bytes)} B/s`;
    }
    function level(value) { return value >= 85 ? "告警" : value >= 70 ? "关注" : "正常"; }

    function updateMetric(metric, renderChart = true, notify = true) {
        byId("cpuValue").textContent = metric.cpu.toFixed(1);
        byId("memoryValue").textContent = metric.memory.toFixed(1);
        byId("diskValue").textContent = metric.disk.toFixed(1);
        byId("cpuProgress").style.width = `${metric.cpu}%`;
        byId("memoryProgress").style.width = `${metric.memory}%`;
        byId("diskProgress").style.width = `${metric.disk}%`;
        byId("cpuLevel").textContent = level(metric.cpu);
        byId("memoryLevel").textContent = level(metric.memory);
        byId("diskLevel").textContent = level(metric.disk);
        byId("cpuCores").textContent = `${metric.cpu_cores} 逻辑核心`;
        byId("cpuFrequency").textContent = metric.cpu_frequency_mhz ? `${Math.round(metric.cpu_frequency_mhz)} MHz` : "频率未知";
        byId("memoryUsed").textContent = `${bytesToGiB(metric.memory_used)} GB 已用`;
        byId("memoryTotal").textContent = `共 ${bytesToGiB(metric.memory_total)} GB`;
        byId("diskUsed").textContent = `${bytesToGiB(metric.disk_used)} / ${bytesToGiB(metric.disk_total)} GB`;
        byId("diskIo").textContent = `R ${formatRate(metric.disk_read)} / W ${formatRate(metric.disk_write)}`;
        byId("netIn").textContent = formatRate(metric.net_in);
        byId("netOut").textContent = formatRate(metric.net_out);
        byId("lastTime").textContent = metric.time.slice(11);

        state.times.push(metric.time);
        state.cpu.push(metric.cpu);
        state.memory.push(metric.memory);
        state.netIn.push(Math.round((metric.net_in || 0) / 1024));
        while (state.times.length > MAX_POINTS) {
            state.times.shift(); state.cpu.shift(); state.memory.shift(); state.netIn.shift();
        }
        state.processes = metric.top_processes || state.processes;
        renderProcesses();
        renderClusters(metric.service_clusters || []);
        updateHealth(metric);
        if (notify) maybePushAdvice(metric);
        state.latestMetric = metric;
        if (renderChart) renderTrend();
    }

    function renderTrend() {
        chart.setOption({ xAxis: { data: state.times }, series: [{ data: state.cpu }, { data: state.memory }, { data: state.netIn }] });
    }

    function renderProcesses() {
        const rows = state.processes[state.processTab] || [];
        const table = byId("processTable");
        table.replaceChildren();
        if (!rows.length) {
            const row = table.insertRow();
            const cell = row.insertCell(); cell.colSpan = 5; cell.textContent = "暂无可读取的进程数据";
            return;
        }
        rows.forEach((process) => {
            const row = table.insertRow();
            [process.name, process.pid, process.username, `${process.cpu.toFixed(1)}%`, `${process.memory.toFixed(1)}%`].forEach((value) => {
                const cell = row.insertCell(); cell.textContent = value;
            });
        });
    }

    function renderClusters(clusters) {
        const container = byId("serviceClusters");
        container.replaceChildren();
        if (!clusters.length) {
            const empty = document.createElement("p");
            empty.className = "empty-state";
            empty.textContent = "该远程节点尚未配置中间件采集器；服务器系统指标仍在实时采集。";
            container.appendChild(empty);
            byId("clusterMode").textContent = "等待真实中间件接入";
            return;
        }
        byId("clusterMode").textContent = state.serverId ? "远程集群节点" : "本机集群节点";
        clusters.forEach((cluster) => {
            const card = document.createElement("article"); card.className = "cluster-card";
            const header = document.createElement("header");
            const title = document.createElement("h4"); title.textContent = cluster.name;
            const status = document.createElement("span"); status.textContent = cluster.status === "healthy" ? "HEALTHY" : "ATTENTION";
            header.append(title, status);
            const summary = document.createElement("div"); summary.className = "cluster-summary";
            const metrics = Object.entries(cluster.metrics || {}).slice(0, 2).map(([key, value]) => `${key}: ${value}`).join(" · ");
            summary.textContent = `${cluster.nodes.length} 节点 · ${metrics}`;
            const nodes = document.createElement("div"); nodes.className = "cluster-nodes";
            cluster.nodes.slice(0, 4).forEach((node) => {
                const row = document.createElement("div"); row.className = "cluster-node";
                const name = document.createElement("span"); name.textContent = node.role;
                const cpu = document.createElement("span"); cpu.textContent = `CPU ${node.cpu.toFixed(1)}%`;
                const memory = document.createElement("span"); memory.textContent = `${Math.round(node.memory_mb)} MB`;
                row.append(name, cpu, memory); nodes.appendChild(row);
            });
            card.append(header, summary, nodes);
            container.appendChild(card);
        });
    }

    function updateHealth(metric) {
        const peak = Math.max(metric.cpu, metric.memory, metric.disk);
        const score = Math.max(0, Math.round(100 - Math.max(0, peak - 45) * 0.75));
        byId("healthScore").textContent = score;
        byId("healthTitle").textContent = peak >= 85 ? "资源压力较高" : peak >= 70 ? "系统需要关注" : "系统运行健康";
    }

    function metricBand(metric) {
        const peak = Math.max(metric.cpu, metric.memory, metric.disk);
        return peak >= 85 ? "critical" : peak >= 70 ? "warning" : "healthy";
    }

    function buildAdvice(metric, recovered = false) {
        const parts = [`当前 CPU ${metric.cpu.toFixed(1)}%，内存 ${metric.memory.toFixed(1)}%，磁盘 ${metric.disk.toFixed(1)}%。`];
        if (metric.cpu >= 85) parts.push("CPU 高负载，建议检查高占用进程、Flink 并行度与 Slot 分配。");
        else if (metric.memory >= 85) parts.push("内存压力较高，建议检查进程堆内存和 TaskManager 内存配置。");
        else if (metric.disk >= 85) parts.push("磁盘容量告警，建议清理日志、检查 Checkpoint 保留策略并扩容存储。");
        else if (Math.max(metric.cpu, metric.memory, metric.disk) >= 70) parts.push("资源负载进入关注区间，建议观察持续趋势并提前制定扩容计划。");
        else if (recovered) parts.push("资源已恢复健康，建议复盘刚才的任务和进程变化。");
        else parts.push("核心资源处于健康区间，目前无需干预。@Jix 将持续值守。");
        return parts.join("");
    }

    function appendMessage(role, text, labelText) {
        const container = byId("assistantMessages");
        const item = document.createElement("div");
        item.className = `message ${role === "user" ? "user-message" : "bot-message"}`;
        const label = document.createElement("span");
        label.textContent = labelText || (role === "user" ? "你" : "@Jix · 刚刚");
        const body = document.createElement("p");
        body.textContent = text;
        item.append(label, body);
        container.appendChild(item);
        while (container.children.length > 12) container.removeChild(container.firstElementChild);
        container.scrollTop = container.scrollHeight;
    }

    function maybePushAdvice(metric) {
        const band = metricBand(metric);
        const now = Date.now();
        if (state.lastBand === null) {
            if (band !== "healthy") {
                appendMessage("bot", `干预提醒：${buildAdvice(metric)}`);
                state.lastAdviceAt = now;
            }
        } else if (band !== state.lastBand) {
            appendMessage("bot", band === "healthy" ? buildAdvice(metric, true) : `干预提醒：${buildAdvice(metric)}`);
            state.lastAdviceAt = now;
        } else if (state.latestMetric && now - state.lastAdviceAt > 30000) {
            if (Math.abs(metric.cpu - state.latestMetric.cpu) >= 12 || Math.abs(metric.memory - state.latestMetric.memory) >= 8) {
                appendMessage("bot", `检测到资源明显波动。${buildAdvice(metric)}`);
                state.lastAdviceAt = now;
            }
        }
        state.lastBand = band;
    }

    async function askJix(question) {
        const response = await fetch("/api/jix/chat/", {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-CSRFToken": getCookie("csrftoken") },
            body: JSON.stringify({ question })
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail || "@Jix 暂时无法回答");
        return result.answer;
    }

    function getCookie(name) {
        const found = document.cookie.split(";").map((item) => item.trim()).find((item) => item.startsWith(`${name}=`));
        return found ? decodeURIComponent(found.split("=").slice(1).join("=")) : "";
    }

    function setConnection(status, label) {
        const node = byId("connectionState");
        node.className = `connection ${status}`;
        node.querySelector("span").textContent = label;
    }

    function connect() {
        const version = ++state.wsVersion;
        if (state.socket) state.socket.close();
        const protocol = location.protocol === "https:" ? "wss" : "ws";
        const path = state.serverId ? `/ws/metrics/${state.serverId}/` : "/ws/metrics/";
        const socket = new WebSocket(`${protocol}://${location.host}${path}`);
        state.socket = socket;
        socket.onopen = () => setConnection("online", "Agent 实时在线");
        socket.onmessage = (event) => {
            const message = JSON.parse(event.data);
            if (message.type === "metrics.history") {
                state.times = []; state.cpu = []; state.memory = []; state.netIn = [];
                state.latestMetric = null; state.lastBand = null;
                message.metrics.slice(-MAX_POINTS).forEach((metric) => updateMetric(metric, false, false));
                if (state.latestMetric) maybePushAdvice(state.latestMetric);
                renderTrend();
            } else if (message.type === "metrics.update") updateMetric(message.metric);
            else if (message.type === "jix.report") appendMessage("bot", message.report, "@Jix · 定期巡检");
        };
        socket.onerror = () => setConnection("offline", "连接异常");
        socket.onclose = () => {
            if (version !== state.wsVersion) return;
            setConnection("offline", "Agent 已断开，正在重连");
            clearTimeout(state.reconnectTimer);
            state.reconnectTimer = setTimeout(connect, 2500);
        };
    }

    async function loadServers() {
        const response = await fetch("/api/servers/");
        const payload = await response.json();
        state.servers = payload.results || payload;
        const select = byId("serverSelect");
        select.replaceChildren();
        state.servers.forEach((server) => {
            const option = document.createElement("option");
            option.value = server.is_local ? "" : server.id;
            option.textContent = `${server.name}${server.is_local ? "" : ` · ${server.ip}`}`;
            select.appendChild(option);
        });
        renderServerList();
    }

    function renderServerList() {
        const list = byId("serverList"); list.replaceChildren();
        state.servers.forEach((server) => {
            const item = document.createElement("div"); item.className = "server-item";
            const info = document.createElement("div");
            const name = document.createElement("strong"); name.textContent = server.name;
            const detail = document.createElement("span"); detail.textContent = server.is_local ? "本机 Agent · 在线" : `${server.username}@${server.ip}:${server.port} · ${server.last_status}`;
            info.append(name, detail);
            const actions = document.createElement("div"); actions.className = "server-item-actions";
            if (!server.is_local) {
                const test = document.createElement("button"); test.type = "button"; test.dataset.testServer = server.id; test.textContent = "测试";
                const remove = document.createElement("button"); remove.type = "button"; remove.dataset.deleteServer = server.id; remove.textContent = "删除";
                actions.append(test, remove);
            }
            item.append(info, actions); list.appendChild(item);
        });
    }

    document.querySelectorAll("[data-process-tab]").forEach((button) => button.addEventListener("click", () => {
        state.processTab = button.dataset.processTab;
        document.querySelectorAll("[data-process-tab]").forEach((item) => item.classList.toggle("active", item === button));
        renderProcesses();
    }));
    window.addEventListener("resize", () => chart.resize());
    byId("assistantForm").addEventListener("submit", async (event) => {
        event.preventDefault();
        const input = byId("assistantQuestion");
        const question = input.value.trim();
        if (!question) return;
        appendMessage("user", question);
        input.value = "";
        input.disabled = true;
        try { appendMessage("bot", await askJix(question)); }
        catch (error) { appendMessage("bot", `${error.message}。我仍在持续采集服务器指标，请稍后重试。`); }
        finally { input.disabled = false; input.focus(); }
    });
    byId("serverSelect").addEventListener("change", (event) => {
        state.serverId = event.target.value;
        const selected = state.servers.find((server) => String(server.id) === state.serverId) || state.servers.find((server) => server.is_local);
        byId("serverLabel").textContent = selected && !selected.is_local ? `REMOTE SERVER / ${selected.ip}` : "LOCAL SERVER / 本机节点";
        byId("serverTitle").textContent = selected ? `${selected.name} 运行态势` : "系统运行态势";
        state.times = []; state.cpu = []; state.memory = []; state.netIn = []; state.latestMetric = null; state.lastBand = null;
        connect();
    });
    byId("manageServers").addEventListener("click", () => byId("serverDialog").showModal());
    byId("closeServerDialog").addEventListener("click", () => byId("serverDialog").close());
    byId("serverForm").addEventListener("submit", async (event) => {
        event.preventDefault();
        const form = event.currentTarget;
        const data = Object.fromEntries(new FormData(form).entries());
        delete data.csrfmiddlewaretoken; data.port = Number(data.port);
        const response = await fetch("/api/servers/", { method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": getCookie("csrftoken") }, body: JSON.stringify(data) });
        byId("serverFormStatus").textContent = response.ok ? "服务器已添加，可点击测试验证 SSH。" : "添加失败，请检查字段。";
        if (response.ok) { form.reset(); form.elements.port.value = 22; await loadServers(); }
    });
    byId("serverList").addEventListener("click", async (event) => {
        const testId = event.target.dataset.testServer;
        const deleteId = event.target.dataset.deleteServer;
        if (testId) {
            event.target.disabled = true; event.target.textContent = "测试中";
            const response = await fetch(`/api/servers/${testId}/test_connection/`, { method: "POST", headers: { "X-CSRFToken": getCookie("csrftoken") } });
            const result = await response.json(); alert(result.message); await loadServers();
        } else if (deleteId && confirm("确认删除这台服务器配置？")) {
            await fetch(`/api/servers/${deleteId}/`, { method: "DELETE", headers: { "X-CSRFToken": getCookie("csrftoken") } });
            await loadServers();
        }
    });
    byId("inspectNow").addEventListener("click", async (event) => {
        event.target.disabled = true; event.target.textContent = "巡检中";
        try {
            const response = await fetch("/api/jix/inspect/", { method: "POST", headers: { "X-CSRFToken": getCookie("csrftoken") } });
            const report = await response.json();
            appendMessage("bot", `${report.problem}。${(report.suggestions || []).join("；")} ${(report.code_optimizations || []).join("；")}`, "@Jix · 立即巡检");
        } finally { event.target.disabled = false; event.target.textContent = "立即巡检"; }
    });
    loadServers().catch(() => {}).finally(connect);
})();
