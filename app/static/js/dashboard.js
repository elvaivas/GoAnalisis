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
    
    // --- REPARACIÓN BOTÓN REPORTE ---
    const btnReport = document.getElementById('btn-open-report');
    if (btnReport) {
        // Eliminamos listeners anteriores (clonando) para evitar duplicados si se recarga
        const newBtn = btnReport.cloneNode(true);
        btnReport.parentNode.replaceChild(newBtn, btnReport);
        
        newBtn.addEventListener('click', (e) => {
            e.preventDefault();
            // Construimos la URL base sin parámetros primero
            let url = '/report';
            // Obtenemos los parámetros actuales del filtro usando la función helper
            const params = buildUrl('').search; 
            // Abrimos en nueva pestaña
            window.open(url + params, '_blank');
        });
    }

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
        updateOrderTypeChart(data.total_deliveries, data.total_pickups);
    }

    async function updateRecentOrdersTable() {
        const res = await authFetch(buildUrl('/api/data/orders'));
        if (!res) return;
        const data = await res.json();
        
        const tableBody = document.getElementById('recent-orders-table-body');
        if (!tableBody) return;
        
        // --- HELPER: Limpieza de Tiempo Regex (Para Entregados/Cancelados) ---
        const cleanFinalTime = (text) => {
            if (!text) return "0m";
            try {
                // Buscamos patrones: "X Horas Y Minutos"
                const hMatch = text.match(/(\d+)\s*Horas?/i);
                const mMatch = text.match(/(\d+)\s*Minutos?/i);
                const sMatch = text.match(/(\d+)\s*segundos?/i);
                
                let h = hMatch ? parseInt(hMatch[1]) : 0;
                let m = mMatch ? parseInt(mMatch[1]) : 0;
                
                let out = "";
                if (h > 0) out += `${h}h `;
                out += `${m}m`;
                return out;
            } catch (e) { return text; }
        };

        let html = '';
        
        data.forEach(o => {
            // 1. ESTADO & COLOR
            let statusBadge = '';
            let isFinal = false;
            
            if (o.current_status === 'delivered') {
                statusBadge = '<span class="badge bg-success bg-opacity-10 text-success border border-success border-opacity-25">ENTREGADO</span>';
                isFinal = true;
            } else if (o.current_status === 'canceled') {
                statusBadge = '<span class="badge bg-danger bg-opacity-10 text-danger border border-danger border-opacity-25">CANCELADO</span>';
                isFinal = true;
            } else if (o.current_status === 'on_the_way') {
                statusBadge = '<span class="badge bg-info text-white animate-pulse">EN CAMINO</span>';
            } else {
                const trans = statusTranslations[o.current_status] || o.current_status.toUpperCase();
                statusBadge = `<span class="badge bg-secondary bg-opacity-25 text-dark">${trans}</span>`;
            }

            // 2. LEALTAD CLIENTE (CRM)
            let tierBadge = '<span class="badge rounded-pill bg-light text-muted border">Nuevo</span>';
            const count = o.customer_orders_count || 1;
            if (count > 10) tierBadge = '<span class="badge rounded-pill bg-warning text-dark border border-warning"><i class="fa-solid fa-crown me-1"></i>VIP</span>';
            else if (count > 1) tierBadge = '<span class="badge rounded-pill bg-primary bg-opacity-10 text-primary border border-primary border-opacity-25">Frecuente</span>';

            // 3. TIEMPO (Cronómetro vs Estático)
            let timeHtml = '';
            if (isFinal) {
                // TIEMPO FINAL LIMPIO
                const finalTime = cleanFinalTime(o.duration_text);
                timeHtml = `<div class="fw-bold text-dark fs-6">${finalTime}</div><small class="text-muted" style="font-size:0.7rem">Tiempo Total</small>`;
            } else {
                // CRONÓMETRO VIVO
                timeHtml = `
                    <div class="live-timer-container" data-created="${o.created_at}" data-state-start="${o.state_start_at}">
                        <div class="fw-bold text-dark fs-5 timer-total font-monospace">--:--</div>
                        <small class="text-muted" style="font-size:0.65rem">En fase: <span class="timer-state text-primary fw-bold">--:--</span></small>
                    </div>`;
            }

            // 4. DATOS LOGÍSTICOS
            const typeBadge = o.order_type === 'Delivery' 
                ? '<span class="badge bg-primary bg-opacity-10 text-primary mb-1"><i class="fa-solid fa-motorcycle me-1"></i>Delivery</span>'
                : '<span class="badge bg-warning bg-opacity-10 text-warning mb-1"><i class="fa-solid fa-person-walking me-1"></i>Pickup</span>';
            
            const driverHtml = o.driver && o.driver.name !== 'No Asignado' 
                ? `<div class="d-flex align-items-center small text-dark"><i class="fa-solid fa-helmet-safety me-2 text-muted"></i>${o.driver.name}</div>`
                : `<div class="small text-muted fst-italic">--</div>`;

            // RENDER FILA
            html += `
                <tr style="border-bottom: 1px solid #f3f4f6;">
                    <!-- COL 1: ID & TIENDA -->
                    <td class="ps-4">
                        <div class="fw-bold text-dark mb-1">#${o.external_id}</div>
                        <span class="badge bg-light text-secondary border fw-normal" style="font-size:0.7rem">${o.store_name}</span>
                    </td>
                    
                    <!-- COL 2: CLIENTE -->
                    <td>
                        <div class="fw-bold text-dark" style="font-size: 0.95rem;">${o.customer_name}</div>
                        <div class="d-flex align-items-center mt-1 gap-2">
                            ${tierBadge}
                            ${o.customer_phone ? `<a href="https://wa.me/${o.customer_phone.replace(/\D/g,'')}" target="_blank" class="text-success small text-decoration-none"><i class="fa-brands fa-whatsapp"></i></a>` : ''}
                        </div>
                    </td>

                    <!-- COL 3: LOGÍSTICA -->
                    <td>
                        ${typeBadge}
                        ${driverHtml}
                    </td>

                    <!-- COL 4: ESTADO & TIEMPO -->
                    <td>
                        <div class="d-flex justify-content-between align-items-center">
                            <div class="me-3">${statusBadge}</div>
                            <div class="text-end">${timeHtml}</div>
                        </div>
                    </td>

                    <!-- COL 5: TOTAL -->
                    <td class="text-end pe-4">
                        <div class="fw-bold text-dark fs-6">$${(o.total_amount||0).toFixed(2)}</div>
                    </td>
                </tr>
            `;
        });
        
        tableBody.innerHTML = html;
        startLiveTimers(); // Reactivar cronómetros para los vivos
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
    
    function updateOrderTypeChart(d, p) {
        const ctx = document.getElementById('orderTypeChart')?.getContext('2d');
        if(!ctx) return;
        if (orderTypeChart) orderTypeChart.destroy();
        orderTypeChart = new Chart(ctx, {
            type: 'doughnut', 
            data: { 
                labels: ['Delivery', 'Retiro'], 
                datasets: [{ 
                    data: [d, p], 
                    backgroundColor: ['#3b82f6', '#f59e0b'], 
                    borderWidth: 0 
                }] 
            },
            options: { 
                cutout: '70%', 
                maintainAspectRatio: false, 
                plugins: { legend: { display: false } } // Oculto leyenda por espacio
            }
        });
    }

    async function updateBottleneckChart() {
        try {
            const ctxDelivery = document.getElementById('bottleneckChart')?.getContext('2d');
            const ctxPickup = document.getElementById('bottleneckPickupChart')?.getContext('2d');

            if (!ctxDelivery && !ctxPickup) return; 

            const res = await authFetch(buildUrl('/api/analysis/bottlenecks'));
            if (!res) return;
            const data = await res.json();
            
            // 1. CONFIGURACIÓN VISUAL
            // Definimos el orden estricto en que queremos ver las barras
            const localStatusOrder = [
                'pending', 'processing', 'confirmed', 'driver_assigned', 'on_the_way', 
                'delivered', 'canceled'
            ];
            
            const localTranslations = {
                'pending': 'Pendiente', 
                'processing': 'Facturando', 
                'confirmed': 'Solicitando',
                'driver_assigned': 'Asignado', 
                'on_the_way': 'En Camino', 
                'delivered': 'Entregado (Total)', 
                'canceled': 'Cancelado (Promedio)'
            };

            const processData = (list) => {
                if (!Array.isArray(list)) return { labels: [], values: [], colors: [] };
                
                // Ordenamos según la lista maestra
                const sorted = list
                    .filter(d => d.avg_duration_seconds > 0)
                    .sort((a, b) => localStatusOrder.indexOf(a.status) - localStatusOrder.indexOf(b.status));

                const labels = sorted.map(d => localTranslations[d.status] || d.status);
                const values = sorted.map(d => (d.avg_duration_seconds / 60).toFixed(1)); // Minutos
                
                // Colores Semánticos
                const colors = sorted.map(d => {
                    if (d.status === 'canceled') return '#ef4444'; // Rojo Cancelado
                    if (d.status === 'delivered') return '#10b981'; // Verde Total
                    return ctxPickup ? '#3b82f6' : '#f59e0b'; // Azul o Naranja para pasos
                });

                return { labels, values, colors };
            };

            // 2. RENDER DELIVERY
            if (ctxDelivery) {
                const dData = processData(data.delivery);
                const dColors = dData.labels.map((l, i) => {
                     if (l.includes('Cancelado')) return '#ef4444';
                     if (l.includes('Entregado')) return '#10b981';
                     return '#f59e0b'; 
                });

                if (bottleneckChart) bottleneckChart.destroy();
                bottleneckChart = new Chart(ctxDelivery, {
                    type: 'bar', 
                    data: { 
                        labels: dData.labels, 
                        datasets: [{ label: 'Minutos', data: dData.values, backgroundColor: dColors, borderRadius: 4 }] 
                    },
                    options: { indexAxis: 'y', maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { display: false } } }
                });
            }

            // 3. RENDER PICKUP
            if (ctxPickup) {
                const pData = processData(data.pickup);
                const pColors = pData.labels.map((l, i) => {
                     if (l.includes('Cancelado')) return '#ef4444';
                     if (l.includes('Entregado')) return '#10b981';
                     return '#3b82f6'; 
                });

                if (bottleneckPickupChart) bottleneckPickupChart.destroy();
                bottleneckPickupChart = new Chart(ctxPickup, {
                    type: 'bar', 
                    data: { 
                        labels: pData.labels, 
                        datasets: [{ label: 'Minutos', data: pData.values, backgroundColor: pColors, borderRadius: 4 }] 
                    },
                    options: { indexAxis: 'y', maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { display: false } } }
                });
            }
        } catch (error) {
            console.error("⚠️ Error renderizando gráficos de tiempos:", error);
        }
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

    // --- 4. TENDENCIAS (Gráfico Mixto: $ + Pedidos + Tiempo) ---
    async function updateTrendsChart() {
        const ctx = document.getElementById('trendsChart')?.getContext('2d');
        if(!ctx) return;

        const res = await authFetch(buildUrl('/api/data/trends'));
        if (!res) return;
        const data = await res.json();

        if (trendsChart) trendsChart.destroy();
        
        trendsChart = new Chart(ctx, {
            type: 'bar',
            data: { 
                labels: data.labels, 
                datasets: [
                    { 
                        type: 'line',
                        label: 'Ingresos ($)', 
                        data: data.revenue, 
                        borderColor: '#10b981', // Verde
                        backgroundColor: 'rgba(16, 185, 129, 0.1)', 
                        yAxisID: 'y', 
                        fill: true,
                        tension: 0.3,
                        order: 1
                    }, 
                    { 
                        type: 'bar',
                        label: 'Pedidos', 
                        data: data.orders, 
                        backgroundColor: 'rgba(59, 130, 246, 0.6)', // Azul
                        borderColor: '#3b82f6', 
                        borderWidth: 1, 
                        yAxisID: 'y1', 
                        order: 2 
                    }, 
                    { 
                        type: 'line',
                        label: 'Tiempo (min)', 
                        data: data.avg_times, 
                        borderColor: '#ef4444', // Rojo
                        backgroundColor: 'transparent', 
                        yAxisID: 'y1', 
                        borderDash: [5,5], 
                        pointRadius: 0,
                        order: 0 
                    }
                ] 
            },
            options: { 
                responsive: true, 
                maintainAspectRatio: false, 
                interaction: { mode: 'index', intersect: false }, 
                scales: { 
                    y: { 
                        display: true, position: 'left', grid: { color: '#e5e7eb' },
                        title: { display: true, text: 'Facturación ($)' }
                    }, 
                    y1: { 
                        display: true, position: 'right', grid: { display: false },
                        title: { display: true, text: 'Pedidos / Minutos' }
                    } 
                }, 
                plugins: { legend: { labels: { usePointStyle: true } } } 
            }
        });
    }

    // --- 5. TOP REPARTIDORES (Leaderboard) ---
    async function updateDriverLeaderboard() {
        const ctx = document.getElementById('driverLeaderboardChart')?.getContext('2d');
        if(!ctx) return;

        const res = await authFetch(buildUrl('/api/data/driver-leaderboard'));
        if (!res) return;
        const data = await res.json();

        if (driverLeaderboardChart) driverLeaderboardChart.destroy();
        
        // Lógica de colores según estado
        const bgColors = data.map(d => {
            if (d.status === 'new') return '#3b82f6';    // Azul (Nuevo)
            if (d.status === 'active') return '#10b981'; // Verde (Activo)
            if (d.status === 'warning') return '#f59e0b';// Amarillo (Alerta)
            return '#ef4444';                            // Rojo (Inactivo)
        });

        const labels = data.map(d => {
            let timeMsg = d.days_inactive === 0 ? "Hoy" : `${d.days_inactive}d`;
            if (d.days_inactive === -1) timeMsg = "Nuevo";
            return `${d.name} (${timeMsg})`;
        });

        driverLeaderboardChart = new Chart(ctx, {
            type: 'bar', 
            data: { 
                labels: labels, 
                datasets: [{ 
                    label: 'Entregas', 
                    data: data.map(d => d.orders), 
                    backgroundColor: bgColors,
                    borderRadius: 4
                }] 
            },
            options: { 
                indexAxis: 'y', 
                maintainAspectRatio: false, 
                scales: { x: { grid: { color: '#e5e7eb' } } }, 
                plugins: { legend: { display: false } } 
            }
        });
    }

    // --- 6. TOP TIENDAS (Lista HTML) ---
    async function updateTopStoresList() {
        const list = document.getElementById('top-stores-list');
        if(!list) return;

        const res = await authFetch(buildUrl('/api/data/top-stores'));
        if (!res) return;
        const data = await res.json();
        
        list.innerHTML = '';
        data.slice(0, 10).forEach(s => { 
            list.innerHTML += `
                <li class="list-group-item d-flex justify-content-between align-items-center px-3 py-2">
                    <div class="d-flex flex-column">
                        <span class="text-dark fw-bold small">
                            <i class="fa-solid fa-store me-2 text-muted"></i>${s.name}
                        </span>
                        <small class="text-muted ms-4" style="font-size: 0.65rem;">
                            Desde: ${s.first_seen}
                        </small>
                    </div>
                    <span class="badge bg-success bg-opacity-10 text-success rounded-pill border border-success border-opacity-25">
                        ${s.orders}
                    </span>
                </li>`; 
        });
    }

    // --- 7. MAPA DE CALOR (Leaflet) ---
    async function updateHeatmap() {
        const mapDiv = document.getElementById('heatmapContainer');
        if (!mapDiv) return;

        // CHECK DE SEGURIDAD: Si el div está oculto (altura 0), NO dibujamos nada para evitar el error IndexSizeError
        if (mapDiv.clientHeight === 0 || mapDiv.clientWidth === 0) {
            console.warn("⚠️ Mapa oculto: Saltando renderizado para evitar crash.");
            return; 
        }

        // Inicialización única
        if (!mapInstance) {
            mapInstance = L.map('heatmapContainer').setView([10.4806, -66.9036], 12);
            L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', { maxZoom: 19 }).addTo(mapInstance);
        }

        // Forzamos ajuste de tamaño
        mapInstance.invalidateSize();

        const res = await authFetch(buildUrl('/api/data/heatmap'));
        if (!res) return;
        const data = await res.json();

        // Limpieza de capa anterior
        if (heatLayer) {
            mapInstance.removeLayer(heatLayer);
            heatLayer = null;
        }

        if (data && data.length > 0) {
            try {
                // Validación extra antes de pintar
                if (mapInstance.getSize().x > 0) {
                    heatLayer = L.heatLayer(data, { 
                        radius: 20, 
                        blur: 15, 
                        maxZoom: 14, 
                        minOpacity: 0.4,
                        gradient: {0.4: 'cyan', 0.65: 'lime', 1: 'red'} 
                    }).addTo(mapInstance);
                    
                    if (data.length > 1) {
                        const bounds = data.map(p => [p[0], p[1]]);
                        mapInstance.fitBounds(bounds, { padding: [20, 20] });
                    }
                }
            } catch(e) { 
                console.error("Error pintando heatmap (posiblemente oculto):", e); 
            }
        }

        // Cargar Tiendas
        try {
            const resStores = await authFetch('/api/data/stores-locations');
            if(resStores) {
                const stores = await resStores.json();
                stores.forEach(s => {
                    L.circleMarker([s.lat, s.lng], { 
                        radius: 5, fillColor: "#fff", color: "#3b82f6", weight: 2, fillOpacity: 1 
                    }).bindPopup(`<b>${s.name}</b>`).addTo(mapInstance);
                });
            }
        } catch(e) {}
    }

    // --- 8. FILTRO DE TIENDAS (Dropdown) ---
    async function loadStoreFilterOptions() {
        const sel = document.getElementById('store-filter');
        if(!sel) return;

        console.log("🏪 Cargando lista de tiendas...");

        // FIX: La ruta correcta debe incluir /data/
        const res = await authFetch('/api/data/all-stores-names');
        
        if (!res || !res.ok) {
            console.error("❌ Error cargando tiendas. Ruta no encontrada o error servidor.");
            sel.innerHTML = '<option value="">Error al cargar</option>';
            return;
        }

        const data = await res.json();
        console.log(`✅ ${data.length} tiendas encontradas.`);
        
        // Limpiamos y ponemos la opción default
        sel.innerHTML = '<option value="">Todas las Tiendas</option>';
        
        data.forEach(name => {
            const opt = document.createElement('option'); 
            opt.value = name; 
            opt.textContent = name; 
            sel.appendChild(opt);
        });
        
        // Recargar dashboard al cambiar selección
        sel.onchange = function() { 
            console.log("Filtro tienda cambiado a:", sel.value);
            fetchAllData(true); 
        };
    }

    // --- FIX MAPA COLAPSABLE ---
    const mapCollapse = document.getElementById('collapseMap');
    if (mapCollapse) {
        mapCollapse.addEventListener('shown.bs.collapse', function () {
            // Cuando se abre, llamamos a la función ahora que SÍ tiene altura
            updateHeatmap();
        });
    }

    async function fetchAllData(isSearch = false) {
        // Actualizamos hora
        const now = new Date();
        const timeString = now.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
        document.getElementById('last-updated').textContent = timeString;

        // Usamos await para garantizar que los datos críticos carguen primero
        await updateKpis(); 
        await updateRecentOrdersTable();
        
        // Ejecutamos en paralelo los secundarios para velocidad
        updateBottleneckChart();     
        updateCancellationChart();   
        
        // Llamada a las funciones restantes (asegúrate de que estas existan en tu archivo real)
        // Como pusiste "dummy code" en el prompt, asumo que las tienes definidas abajo.
        if (typeof loadTopCustomers === 'function') loadTopCustomers();
        if (typeof updateTopProducts === 'function') updateTopProducts();
        if (typeof updateDriverLeaderboard === 'function') updateDriverLeaderboard();
        if (typeof updateTopStoresList === 'function') updateTopStoresList();
        if (typeof updateHeatmap === 'function') updateHeatmap();
        if (typeof updateTrendsChart === 'function') updateTrendsChart();
    }

    datePicker = flatpickr("#date-range-picker", { mode: "range", dateFormat: "Y-m-d", defaultDate: [new Date(), new Date()], onClose: fetchAllData });
    document.getElementById('btn-update')?.addEventListener('click', () => fetchAllData(true));
    document.getElementById('btn-all-history')?.addEventListener('click', () => { datePicker.setDate(["2024-01-01", new Date()]); fetchAllData(); });
    loadStoreFilterOptions();
    
    fetchAllData();
    setInterval(fetchAllData, 60000);
});
