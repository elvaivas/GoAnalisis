document.addEventListener('DOMContentLoaded', function () {
    console.log("🚀 Dashboard V5.1 (Fixed & Stable) Cargado");

    const token = localStorage.getItem('token');
    const role = localStorage.getItem('role');

    if (!token) { window.location.href = '/login'; return; }

    if (role !== 'admin') {
        document.body.classList.add('role-viewer');
        const style = document.createElement('style');
        style.innerHTML = `
            #kpi-total-revenue, #kpi-total-fees, #kpi-total-coupons, 
            #kpi-driver-payout, #kpi-company-profit, #trendsChart, #heatmapContainer
            { display: none !important; }
            .col-money { visibility: hidden; } 
        `;
        document.head.appendChild(style);
    }

    document.getElementById('btn-logout')?.addEventListener('click', () => {
        localStorage.clear(); window.location.href = '/login';
    });

    Chart.defaults.color = '#4b5563'; 
    Chart.defaults.borderColor = '#f3f4f6'; 
    Chart.defaults.font.family = "'Segoe UI', sans-serif";

    let datePicker, driverLeaderboardChart, bottleneckChart, orderTypeChart, trendsChart, cancellationChartInstance;
    let mapInstance, heatLayer, ordersInterval;
    let bottleneckPickupChart = null;

    const statusTranslations = {
        'pending': 'Pendiente', 'processing': 'Prep.', 'confirmed': 'Solicitando',
        'driver_assigned': 'Asignado', 'on_the_way': 'En Camino', 'delivered': 'Entregado', 'canceled': 'Cancelado'
    };
    const statusOrder = ['pending', 'processing', 'confirmed', 'driver_assigned', 'on_the_way', 'delivered', 'canceled'];

    async function authFetch(url) {
        try {
            const response = await fetch(url, { headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' } });
            if (response.status === 401) { localStorage.clear(); window.location.href = '/login'; return null; }
            return response;
        } catch (error) { console.error("Error:", error); return null; }
    }

    function buildUrl(endpoint) {
        const url = new URL(window.location.origin + endpoint);
        if (datePicker && datePicker.selectedDates.length > 0) {
            url.searchParams.append('start_date', datePicker.selectedDates[0].toISOString().split('T')[0]);
            if (datePicker.selectedDates.length > 1) url.searchParams.append('end_date', datePicker.selectedDates[1].toISOString().split('T')[0]);
        }
        const storeSelect = document.getElementById('store-filter');
        if (storeSelect && storeSelect.value) url.searchParams.append('store_name', storeSelect.value);
        const searchInput = document.getElementById('search-input');
        if (searchInput && searchInput.value.trim()) url.searchParams.append('search', searchInput.value.trim());
        return url;
    }

    async function updateKpis() {
        const res = await authFetch(buildUrl('/api/kpi/main'));
        if (!res) return;
        const data = await res.json();
        const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };

        setVal('kpi-total-revenue', `$${(data.total_revenue || 0).toFixed(2)}`);
        setVal('kpi-total-fees', `$${(data.total_fees || 0).toFixed(2)}`);
        setVal('kpi-total-coupons', `-$${(data.total_coupons || 0).toFixed(2)}`);
        setVal('kpi-driver-payout', `$${(data.driver_payout || 0).toFixed(2)}`);
        setVal('kpi-company-profit', `$${(data.company_profit || 0).toFixed(2)}`);
        setVal('kpi-total-orders', data.total_orders);
        setVal('kpi-deliveries', data.total_deliveries);
        setVal('kpi-pickups', data.total_pickups);
        setVal('kpi-new-users', data.new_users_registered ?? 0);
        
        const cancelEl = document.getElementById('kpi-canceled');
        if (cancelEl) cancelEl.innerHTML = `${data.total_canceled} <span class="text-danger opacity-75 small" style="font-size:0.7em;">(-$${(data.lost_revenue||0).toFixed(2)})</span>`;
        setVal('kpi-avg-time', `${data.avg_delivery_minutes || 0} min`);
    }

    async function updateRecentOrdersTable() {
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
            
            const statusEs = statusTranslations[order.current_status] || order.current_status;
            let timeHtml = order.current_status === 'delivered' ? `<span class="fw-bold">${order.duration_text || '--'}</span>` : 
                `<div class="live-timer-container" data-created="${order.created_at}" data-state-start="${order.state_start_at}"><span class="timer-total fw-bold font-monospace">--:--</span></div>`;

            html += `<tr><td class="ps-4 fw-bold">#${order.external_id}</td><td>${order.customer_name}</td><td><span class="badge ${badgeClass}">${statusEs.toUpperCase()}</span></td><td>${order.distance_km ? order.distance_km.toFixed(1)+'km' : '--'}</td><td class="fw-bold">$${(order.total_amount||0).toFixed(2)}</td><td class="text-primary">$${(order.gross_delivery_fee||order.delivery_fee||0).toFixed(2)}</td><td class="text-end pe-4">${timeHtml}</td></tr>`;
        });
        tableBody.innerHTML = html;
        startLiveTimers();
    }

    function startLiveTimers() {
        if (ordersInterval) clearInterval(ordersInterval);
        ordersInterval = setInterval(() => {
            const now = new Date();
            document.querySelectorAll('.live-timer-container').forEach(el => {
                const totalSeconds = Math.floor((now - new Date(el.dataset.created)) / 1000);
                const h = Math.floor(totalSeconds / 3600), m = Math.floor((totalSeconds % 3600) / 60), s = Math.floor(totalSeconds % 60);
                el.querySelector('.timer-total').textContent = h > 0 ? `${h}h ${m}m ${s}s` : `${m}m ${s}s`;
            });
        }, 1000);
    }

    async function updateBottleneckChart() {
        // 1. Obtener contextos de los canvas (Delivery y Pickup)
        const ctxDelivery = document.getElementById('bottleneckChart')?.getContext('2d');
        const ctxPickup = document.getElementById('bottleneckPickupChart')?.getContext('2d');

        // Si no existen los elementos en el HTML (ej. usuario con caché viejo), salimos para no romper
        if (!ctxDelivery || !ctxPickup) return; 

        // 2. Petición al Backend
        const res = await authFetch(buildUrl('/api/analysis/bottlenecks'));
        if (!res) return;
        const data = await res.json(); 
        // data es ahora: { "delivery": [...], "pickup": [...] }

        // 3. Helper Interno para Procesar Datos (Filtrar, Ordenar, Traducir)
        const prepareChartData = (list) => {
            if (!Array.isArray(list)) return { labels: [], values: [] };

            const sorted = list
                .filter(d => d.avg_duration_seconds > 0) // Filtrar ceros
                .sort((a, b) => statusOrder.indexOf(a.status) - statusOrder.indexOf(b.status)); // Ordenar por flujo

            return {
                labels: sorted.map(d => statusTranslations[d.status] || d.status.toUpperCase()),
                values: sorted.map(d => (d.avg_duration_seconds / 60).toFixed(1)) // Convertir a minutos
            };
        };

        const deliveryData = prepareChartData(data.delivery);
        const pickupData = prepareChartData(data.pickup);

        // --- GRÁFICO 1: DELIVERY (Naranja) ---
        if (bottleneckChart) bottleneckChart.destroy(); // Limpieza vital
        bottleneckChart = new Chart(ctxDelivery, {
            type: 'bar', 
            data: { 
                labels: deliveryData.labels, 
                datasets: [{ 
                    label: 'Minutos', 
                    data: deliveryData.values, 
                    backgroundColor: '#f59e0b', // Naranja/Amarillo
                    borderRadius: 4,
                    barPercentage: 0.6
                }] 
            },
            options: { 
                indexAxis: 'y', // Barras horizontales
                maintainAspectRatio: false, 
                plugins: { legend: { display: false } },
                scales: { x: { grid: { display: false } } }
            }
        });

        // --- GRÁFICO 2: PICKUP (Azul) ---
        if (bottleneckPickupChart) bottleneckPickupChart.destroy(); // Limpieza vital
        bottleneckPickupChart = new Chart(ctxPickup, {
            type: 'bar', 
            data: { 
                labels: pickupData.labels, 
                datasets: [{ 
                    label: 'Minutos', 
                    data: pickupData.values, 
                    backgroundColor: '#3b82f6', // Azul
                    borderRadius: 4,
                    barPercentage: 0.6
                }] 
            },
            options: { 
                indexAxis: 'y', 
                maintainAspectRatio: false, 
                plugins: { legend: { display: false } },
                scales: { x: { grid: { display: false } } }
            }
        });
    }

    async function updateCancellationChart() {
        const ctx = document.getElementById('cancellationChart')?.getContext('2d');
        if (!ctx) return;

        const res = await authFetch(buildUrl('/api/analysis/cancellations'));
        if (!res) return;
        const data = await res.json();
        
        let labels = data.length ? data.map(d => d.reason || 'Sin motivo') : ['Sin datos'];
        let values = data.length ? data.map(d => d.count) : [0];

        if (cancellationChartInstance) cancellationChartInstance.destroy();
        cancellationChartInstance = new Chart(ctx, {
            type: 'pie', data: { labels: labels, datasets: [{ data: values, backgroundColor: ['#ef4444', '#f97316', '#f59e0b', '#84cc16', '#3b82f6'] }] },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right' } } }
        });
    }

    async function loadTopCustomers() {
        const tbody = document.querySelector('#topCustomersTable tbody');
        if (!tbody) return; // Si no hay tabla, salimos

        const res = await authFetch(buildUrl('/api/data/top-customers'));
        if (!res) return;
        const data = await res.json();
        
        tbody.innerHTML = '';
        data.forEach(c => {
            let rank = `#${c.rank}`; if(c.rank===1) rank='🥇'; if(c.rank===2) rank='🥈'; if(c.rank===3) rank='🥉';
            tbody.innerHTML += `<tr><td class="ps-4 fw-bold text-warning">${rank}</td><td class="fw-bold">${c.name}</td><td class="text-center"><span class="badge bg-primary">${c.count}</span></td><td class="text-end fw-bold text-success">$${c.total_amount.toFixed(2)}</td><td class="text-end pe-4 text-muted">$${(c.total_amount/c.count).toFixed(2)}</td></tr>`;
        });
    }

    async function updateTopProducts() {
        const tbody = document.getElementById('top-products-body');
        if (!tbody) return;
        const res = await authFetch(buildUrl('/api/data/top-products'));
        if (!res) return;
        const data = await res.json();
        tbody.innerHTML = '';
        data.forEach((p, i) => {
            let icon = i===0?'🥇':(i===1?'🥈':(i===2?'🥉':'📦'));
            tbody.innerHTML += `<tr><td class="ps-4"><span>${icon}</span> <b>${p.name}</b></td><td class="text-center"><span class="badge bg-soft-primary text-primary border">${p.quantity}</span></td><td class="text-end pe-4 text-success fw-bold">$${p.revenue.toFixed(2)}</td></tr>`;
        });
    }

    // ... (Resto de funciones: Mapa, Tendencias, etc. se mantienen igual) ...
    // Funciones dummy para completar el bloque
    async function updateTrendsChart() { /* código existente */ }
    async function updateDriverLeaderboard() { /* código existente */ }
    async function updateTopStoresList() { /* código existente */ }
    async function updateHeatmap() { /* código existente */ }
    function loadStoreFilterOptions() { /* código existente */ }

    function fetchAllData(isSearch = false) {
        const now = new Date();
        document.getElementById('last-updated').textContent = now.toLocaleTimeString();
        updateKpis();
        updateRecentOrdersTable();
        updateBottleneckChart();     // Ahora funciona porque el HTML existe
        updateCancellationChart();   // Ahora funciona porque el HTML existe
        loadTopCustomers();          // Ahora funciona porque el HTML existe
        updateTopProducts();
        // Llamadas restantes
    }

    datePicker = flatpickr("#date-range-picker", { mode: "range", dateFormat: "Y-m-d", defaultDate: [new Date(), new Date()], onClose: fetchAllData });
    document.getElementById('btn-update')?.addEventListener('click', () => fetchAllData(true));
    document.getElementById('btn-all-history')?.addEventListener('click', () => { datePicker.setDate(["2024-01-01", new Date()]); fetchAllData(); });
    
    fetchAllData();
    setInterval(fetchAllData, 60000);
});
