document.addEventListener('DOMContentLoaded', function () {
    console.log("🚀 Dashboard V5.0 (Seguro) Cargado");

    // --- 1. SEGURIDAD: VERIFICACIÓN DE ACCESO ---
    const token = localStorage.getItem('token');
    const role = localStorage.getItem('role');

    if (!token) {
        console.warn("⛔ No hay token. Redirigiendo al login...");
        window.location.href = '/login';
        return; // Detener ejecución
    }

    // --- 2. GESTIÓN DE ROLES (ATC vs ADMIN) ---
    // Si el rol no es admin, ocultamos elementos sensibles visualmente
    // (El backend también debe proteger los datos)
    if (role !== 'admin') {
        document.body.classList.add('role-viewer');
        console.log("🔒 Modo Visualizador (Datos financieros ocultos)");
        
        // CSS inyectado para ocultar elementos financieros a viewers
        const style = document.createElement('style');
        style.innerHTML = `
            .role-viewer .card-header.text-success, 
            .role-viewer .text-success.fw-bold,
            .role-viewer #kpi-total-revenue,
            .role-viewer #kpi-total-fees,
            .role-viewer #kpi-company-profit,
            .role-viewer #trendsChart { display: none !important; }
        `;
        document.head.appendChild(style);
    }

    // Logout
    document.getElementById('btn-logout')?.addEventListener('click', () => {
        localStorage.clear();
        window.location.href = '/login';
    });

    // --- CONFIGURACIÓN GLOBAL ---
    Chart.defaults.color = '#94a3b8'; 
    Chart.defaults.borderColor = 'rgba(255, 255, 255, 0.05)'; 

    let datePicker, driverLeaderboardChart, bottleneckChart, orderTypeChart, trendsChart, cancellationChartInstance;
    let mapInstance, heatLayer, ordersInterval;

    // --- HELPER: PETICIÓN SEGURA (AUTH FETCH) ---
    // Reemplaza al fetch normal. Inyecta el token automáticamente.
    async function authFetch(url) {
        try {
            const response = await fetch(url, {
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                }
            });

            if (response.status === 401) {
                console.error("⛔ Sesión expirada.");
                localStorage.clear();
                window.location.href = '/login';
                return null;
            }
            return response;
        } catch (error) {
            console.error("Error de red:", error);
            return null;
        }
    }

    function buildUrl(endpoint) {
        const url = new URL(window.location.origin + endpoint);
        if (datePicker && datePicker.selectedDates.length > 0) {
            url.searchParams.append('start_date', datePicker.selectedDates[0].toISOString().split('T')[0]);
            if (datePicker.selectedDates.length > 1) {
                url.searchParams.append('end_date', datePicker.selectedDates[1].toISOString().split('T')[0]);
            }
        }
        const storeSelect = document.getElementById('store-filter');
        if (storeSelect && storeSelect.value) {
            url.searchParams.append('store_name', storeSelect.value);
        }
        const searchInput = document.getElementById('search-input');
        if (searchInput && searchInput.value.trim() !== "") {
            url.searchParams.append('search', searchInput.value.trim());
        }
        return url;
    }

    // --- 1. KPIs ---
    async function updateKpis() {
        const res = await authFetch(buildUrl('/api/kpi/main'));
        if (!res) return;
        const data = await res.json();

        const setVal = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = val;
        };

        // Financieros
        setVal('kpi-total-revenue', `$${(data.total_revenue || 0).toFixed(2)}`);
        setVal('kpi-total-fees', `$${(data.total_fees || 0).toFixed(2)}`);
        setVal('kpi-total-coupons', `-$${(data.total_coupons || 0).toFixed(2)}`);
        setVal('kpi-driver-payout', `$${(data.driver_payout || 0).toFixed(2)}`);
        setVal('kpi-company-profit', `$${(data.company_profit || 0).toFixed(2)}`);

        // Operativos
        setVal('kpi-total-orders', data.total_orders);
        setVal('kpi-deliveries', data.total_deliveries);
        setVal('kpi-pickups', data.total_pickups);
        
        // Cancelados con HTML
        const cancelEl = document.getElementById('kpi-canceled');
        if (cancelEl) {
            const count = data.total_canceled ?? 0;
            const lost = (data.lost_revenue || 0).toFixed(2);
            cancelEl.innerHTML = `${count} <span style="font-size: 0.6em; opacity: 0.8;">(-$${lost})</span>`;
        }
        
        setVal('kpi-avg-time', `${data.avg_delivery_minutes || 0} min`);
        updateOrderTypeChart(data.total_deliveries, data.total_pickups);
    }

    // --- 2. TABLA PEDIDOS ---
    async function updateRecentOrdersTable() {
        const cleanDurationText = (text) => {
            if (!text) return "--";
            try {
                const h = text.match(/(\d+)\s*Horas/i)?.[1] || 0;
                const m = text.match(/(\d+)\s*Minutos/i)?.[1] || 0;
                const s = text.match(/(\d+)\s*segundos/i)?.[1] || 0;
                let result = ""; if (h > 0) result += `${h}h `; result += `${m}m ${s}s`;
                return result;
            } catch (e) { return text; }
        };

        const res = await authFetch(buildUrl('/api/data/orders'));
        if (!res) return;
        const data = await res.json();
        
        const tableBody = document.getElementById('recent-orders-table-body');
        if (!tableBody) return;
        
        let html = '';
        data.forEach(order => {
            let badgeClass = 'bg-secondary';
            if (order.current_status === 'delivered') badgeClass = 'bg-success';
            else if (order.current_status === 'canceled') badgeClass = 'bg-danger';
            else if (order.current_status === 'on_the_way') badgeClass = 'bg-info text-dark animate-pulse';
            else if (order.current_status === 'driver_assigned') badgeClass = 'bg-primary';
            else if (order.current_status === 'processing') badgeClass = 'bg-warning text-dark';
            else if (order.current_status === 'confirmed') badgeClass = 'bg-info bg-opacity-50 text-dark';

            const statusEs = statusTranslations[order.current_status] || order.current_status;
            
            // Cliente + WhatsApp
            let clientHtml = `<span class="fw-bold text-white d-block" style="font-size: 0.9rem;">${order.customer_name || 'Unknown'}</span>`;
            if (order.customer_phone) {
                const rawPhone = order.customer_phone.replace(/\D/g, '');
                clientHtml += `<a href="https://wa.me/${rawPhone}" target="_blank" class="text-success small text-decoration-none"><i class="fa-brands fa-whatsapp me-1"></i>${order.customer_phone}</a>`;
            }

            // Distancia
            let distHtml = '<span class="text-muted small">--</span>';
            if (order.distance_km && order.distance_km > 0) distHtml = `<span class="badge bg-dark border border-secondary text-info">${order.distance_km.toFixed(1)} km</span>`;

            let timeHtml = '';
            if (order.current_status === 'delivered') {
                timeHtml = `<div class="d-flex flex-column align-items-end"><span class="fw-bold text-white fs-6">${cleanDurationText(order.duration_text)}</span><small class="text-success" style="font-size:0.7rem;">COMPLETADO</small></div>`;
            } else if (order.current_status === 'canceled') {
                timeHtml = `<span class="badge bg-danger bg-opacity-25 text-danger border border-danger">CANCELADO</span>`;
            } else {
                timeHtml = `<div class="d-flex flex-column align-items-end live-timer-container" data-created="${order.created_at}" data-state-start="${order.state_start_at}"><span class="fw-bold text-white fs-5 timer-total" style="font-family: monospace;">--:--</span><small class="text-white-50" style="font-size: 0.75rem;">En estado: <span class="timer-state fw-semibold text-info">--:--</span></small></div>`;
            }

            html += `<tr style="border-bottom: 1px solid rgba(255,255,255,0.05);"><td class="ps-4"><span class="fw-bold text-white">#${order.external_id}</span></td><td>${clientHtml}</td><td><span class="badge ${badgeClass}">${statusEs.toUpperCase()}</span></td><td>${distHtml}</td><td class="text-white fw-bold">$${(order.total_amount||0).toFixed(2)}</td><td class="text-success fw-bold">$${(order.delivery_fee||0).toFixed(2)}</td><td class="text-end pe-4">${timeHtml}</td></tr>`;
        });
        tableBody.innerHTML = html;
        startLiveTimers();
    }

    // --- TIMERS ---
    function formatTime(totalSeconds) {
        if (totalSeconds < 0) totalSeconds = 0;
        const h = Math.floor(totalSeconds / 3600);
        const m = Math.floor((totalSeconds % 3600) / 60);
        const s = Math.floor(totalSeconds % 60);
        if (h > 0) return `${h}h ${m}m ${s}s`;
        return `${m}m ${s}s`;
    }

    function startLiveTimers() {
        if (ordersInterval) clearInterval(ordersInterval);
        ordersInterval = setInterval(() => {
            const now = new Date();
            document.querySelectorAll('.live-timer-container').forEach(el => {
                let createdStr = el.dataset.created;
                let stateStr = el.dataset.stateStart;
                if (!stateStr.endsWith('Z')) stateStr += 'Z';
                
                const totalSeconds = Math.floor((now - new Date(createdStr)) / 1000);
                const stateSeconds = Math.floor((now - new Date(stateStr)) / 1000);
                
                const totalEl = el.querySelector('.timer-total');
                const stateEl = el.querySelector('.timer-state');
                
                if(totalEl) totalEl.textContent = formatTime(totalSeconds);
                if(stateEl) stateEl.textContent = formatTime(stateSeconds);
                
                if (totalSeconds > 2700 && totalEl) totalEl.classList.add('text-danger');
            });
        }, 1000);
    }

    // --- MAPA ---
    function initMap() {
        if (mapInstance) return;
        const mapDiv = document.getElementById('heatmapContainer');
        if (!mapDiv) return;
        mapInstance = L.map('heatmapContainer').setView([10.4806, -66.9036], 12);
        L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', { attribution: 'CARTO', maxZoom: 19 }).addTo(mapInstance);
    }

    async function updateHeatmap() {
        initMap();
        if(!mapInstance) return;
        const container = mapInstance.getContainer();
        if (container.clientHeight === 0) return;
        mapInstance.invalidateSize();

        const res = await authFetch(buildUrl('/api/data/heatmap'));
        if (!res) return;
        const data = await res.json();

        if (heatLayer) mapInstance.removeLayer(heatLayer);
        if (data && data.length > 0) {
            try {
                heatLayer = L.heatLayer(data, { radius: 20, blur: 15, maxZoom: 14, max: 0.6, gradient: {0.4: 'cyan', 0.65: 'lime', 1: 'red'} }).addTo(mapInstance);
                const bounds = data.map(p => [p[0], p[1]]);
                if (bounds.length > 0) mapInstance.fitBounds(bounds);
            } catch(e) {}
        }
        
        const resStores = await authFetch('/api/data/stores-locations');
        if(resStores) {
            const stores = await resStores.json();
            stores.forEach(s => {
                L.circleMarker([s.lat, s.lng], { radius: 6, fillColor: "#ffffff", color: "#3b82f6", weight: 2, opacity: 1, fillOpacity: 1 }).bindPopup(`<b>🏪 ${s.name}</b>`).addTo(mapInstance);
            });
        }
    }

    // --- GRÁFICOS VARIOS (Usando authFetch) ---
    async function updateBottleneckChart() {
        const res = await authFetch(buildUrl('/api/analysis/bottlenecks'));
        if (!res) return;
        const data = await res.json();
        
        const filtered = data.filter(d => d.avg_duration_seconds > 0).sort((a, b) => statusOrder.indexOf(a.status) - statusOrder.indexOf(b.status));
        const ctx = document.getElementById('bottleneckChart')?.getContext('2d');
        if(!ctx) return;
        if (bottleneckChart) bottleneckChart.destroy();
        bottleneckChart = new Chart(ctx, {
            type: 'bar', data: { labels: filtered.map(d => statusTranslations[d.status] || d.status.toUpperCase()), datasets: [{ label: 'Min', data: filtered.map(d => (d.avg_duration_seconds/60).toFixed(1)), backgroundColor: '#f59e0b' }] },
            options: { indexAxis: 'y', maintainAspectRatio: false, plugins: { legend: { display: false } } }
        });
    }

    function updateOrderTypeChart(d, p) {
        const ctx = document.getElementById('orderTypeChart')?.getContext('2d');
        if(!ctx) return;
        if (orderTypeChart) orderTypeChart.destroy();
        orderTypeChart = new Chart(ctx, {
            type: 'doughnut', data: { labels: ['Delivery', 'Retiro'], datasets: [{ data: [d, p], backgroundColor: ['#3b82f6', '#f59e0b'], borderWidth: 0 }] },
            options: { cutout: '70%', maintainAspectRatio: false, plugins: { legend: { position: 'bottom', labels: { color: '#f8fafc' } } } }
        });
    }

    async function updateCancellationChart() {
        const res = await authFetch(buildUrl('/api/analysis/cancellations'));
        if (!res) return;
        const data = await res.json();
        const ctx = document.getElementById('cancellationChart')?.getContext('2d');
        if(!ctx) return;
        
        let labels = [], values = [];
        if (data && data.length > 0) { labels = data.map(d => d.reason || 'Sin motivo'); values = data.map(d => d.count); } 
        else { labels = ['Sin datos']; values = [0]; }
        if (cancellationChartInstance) cancellationChartInstance.destroy();
        cancellationChartInstance = new Chart(ctx, {
            type: 'pie', data: { labels: labels, datasets: [{ data: values, backgroundColor: ['#ef4444', '#f97316', '#84cc16', '#3b82f6', '#8b5cf6', '#6366f1'], borderWidth: 0 }] },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right', labels: { color: '#f8fafc', boxWidth: 10 } } } }
        });
    }

    async function updateTrendsChart() {
        const res = await authFetch(buildUrl('/api/data/trends'));
        if (!res) return;
        const data = await res.json();
        const ctx = document.getElementById('trendsChart')?.getContext('2d');
        if(!ctx) return;
        if (trendsChart) trendsChart.destroy();
        trendsChart = new Chart(ctx, {
            type: 'line', data: { labels: data.labels, datasets: [{ label: 'Ingresos', data: data.revenue, borderColor: '#10b981', backgroundColor: 'rgba(16, 185, 129, 0.1)', yAxisID: 'y', fill: true }, { label: 'Pedidos', data: data.orders, backgroundColor: 'rgba(59, 130, 246, 0.5)', borderColor: '#3b82f6', borderWidth: 1, type: 'bar', yAxisID: 'y1', order: 2 }, { label: 'Tiempo (min)', data: data.avg_times, borderColor: '#ef4444', backgroundColor: 'transparent', yAxisID: 'y1', borderDash: [5,5], type: 'line', order: 1 }] },
            options: { responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false }, scales: { y: { display: true, position: 'left', grid: { color: 'rgba(255,255,255,0.05)' } }, y1: { display: true, position: 'right', grid: { display: false } } }, plugins: { legend: { labels: { color: '#f8fafc' } } } }
        });
    }

    async function updateDriverLeaderboard() {
        const res = await authFetch(buildUrl('/api/data/driver-leaderboard'));
        if (!res) return;
        const data = await res.json();
        const ctx = document.getElementById('driverLeaderboardChart')?.getContext('2d');
        if(!ctx) return;
        if (driverLeaderboardChart) driverLeaderboardChart.destroy();
        const bgColors = data.map(d => (d.status === 'active' ? '#10b981' : d.status === 'warning' ? '#f59e0b' : '#ef4444'));
        const labels = data.map(d => `${d.name} (${d.days_inactive}d)`);

        driverLeaderboardChart = new Chart(ctx, {
            type: 'bar', data: { labels: labels, datasets: [{ label: 'Entregas', data: data.map(d => d.orders), backgroundColor: bgColors }] },
            options: { indexAxis: 'y', maintainAspectRatio: false, scales: { x: { grid: { color: 'rgba(255,255,255,0.05)' } } }, plugins: { legend: { display: false } } }
        });
    }

    async function updateTopStoresList() {
        const res = await authFetch(buildUrl('/api/data/top-stores'));
        if (!res) return;
        const data = await res.json();
        const list = document.getElementById('top-stores-list');
        if(!list) return;
        list.innerHTML = '';
        data.forEach(s => { list.innerHTML += `<li class="list-group-item d-flex justify-content-between align-items-center px-4 py-3"><div class="d-flex flex-column"><span class="text-white fw-bold"><i class="fa-solid fa-store me-2 text-muted"></i>${s.name}</span><small class="text-muted ms-4" style="font-size: 0.7rem;">Desde: ${s.first_seen}</small></div><span class="badge bg-success rounded-pill">${s.orders}</span></li>`; });
    }

    async function loadTopCustomers() {
        const res = await authFetch(buildUrl('/api/data/top-customers'));
        if (!res) return;
        const data = await res.json();
        const tbody = document.querySelector('#topCustomersTable tbody');
        if(!tbody) return;
        tbody.innerHTML = '';
        data.forEach((c, i) => {
            let rank = `#${c.rank}`; if(c.rank===1) rank='🥇'; if(c.rank===2) rank='🥈'; if(c.rank===3) rank='🥉';
            tbody.innerHTML += `<tr><td class="ps-4 text-warning fw-bold">${rank}</td><td class="fw-bold text-white">${c.name}</td><td class="text-center"><span class="badge bg-primary text-white">${c.count}</span></td><td class="text-end text-success fw-bold">$${c.total_amount.toFixed(2)}</td><td class="text-end pe-4 text-muted">$${(c.total_amount/c.count).toFixed(2)}</td></tr>`;
        });
    }

    // --- CARGAR FILTROS ---
    async function loadStoreFilterOptions() {
        const res = await authFetch('/api/data/all-stores-names');
        if (!res) return;
        const data = await res.json();
        const sel = document.getElementById('store-filter');
        if(!sel) return;
        sel.innerHTML = '<option value="">Todas las Tiendas</option>';
        data.forEach(name => {
            const opt = document.createElement('option'); opt.value = name; opt.textContent = name; sel.appendChild(opt);
        });
        sel.onchange = function() { fetchAllData(); };
    }

    // --- MAIN ---
    function fetchAllData(isSearch = false) {
        if (isSearch) window.scrollTo({ top: 0, behavior: 'smooth' });
        updateKpis();
        updateBottleneckChart();
        updateRecentOrdersTable();
        updateTrendsChart();
        updateDriverLeaderboard();
        updateTopStoresList();
        loadTopCustomers();
        updateCancellationChart();
        updateHeatmap();
    }

    datePicker = flatpickr("#date-range-picker", { mode: "range", dateFormat: "Y-m-d", theme: "dark", defaultDate: [new Date(), new Date()], onClose: fetchAllData });
    loadStoreFilterOptions();

    // Listeners
    document.getElementById('btn-update')?.addEventListener('click', () => fetchAllData(true));
    document.getElementById('btn-all-history')?.addEventListener('click', () => { datePicker.setDate(["2024-01-01", new Date()]); fetchAllData(); });
    document.getElementById('search-input')?.addEventListener('keypress', (e) => { if (e.key === 'Enter') fetchAllData(true); });
    document.getElementById('btn-clear-search')?.addEventListener('click', () => { 
        document.getElementById('search-input').value = ''; 
        fetchAllData(); 
    });

    const mapCollapse = document.getElementById('collapseMap');
    if (mapCollapse) {
        mapCollapse.addEventListener('shown.bs.collapse', function () {
            if (mapInstance) setTimeout(() => { mapInstance.invalidateSize(); updateHeatmap(); }, 100);
        });
    }

    fetchAllData();
    setInterval(fetchAllData, 60000);
});
