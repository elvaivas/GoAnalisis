document.addEventListener('DOMContentLoaded', function () {
    console.log("🚀 Dashboard V3.3 Cargado (Full)");
    
    // --- CONFIGURACIÓN GLOBAL CHART.JS ---
    Chart.defaults.color = '#94a3b8'; 
    Chart.defaults.borderColor = 'rgba(255, 255, 255, 0.05)'; 

    // --- VARIABLES GLOBALES ---
    let datePicker;
    let driverLeaderboardChart, bottleneckChart, orderTypeChart, trendsChart, cancellationChartInstance;
    let mapInstance, heatLayer;
    let ordersInterval;

    // --- TRADUCCIONES Y ORDEN ---
    const statusOrder = ['pending', 'processing', 'confirmed', 'driver_assigned', 'on_the_way', 'delivered', 'canceled'];
    
    const today = new Date();
    
    const statusTranslations = {
        'pending': 'Pendiente',
        'processing': 'Facturando',
        'confirmed': 'Solicitando Motorizado', // <--- CAMBIO CLAVE
        'driver_assigned': 'Motorizado Asignado',
        'on_the_way': 'En Camino',
        'delivered': 'Entregado',
        'canceled': 'Cancelado'
    };

    // --- HELPER URL ---
    function buildUrl(endpoint) {
        const url = new URL(window.location.origin + endpoint);
        
        // Filtro Fecha
        if (datePicker && datePicker.selectedDates.length > 0) {
            url.searchParams.append('start_date', datePicker.selectedDates[0].toISOString().split('T')[0]);
            if (datePicker.selectedDates.length > 1) {
                url.searchParams.append('end_date', datePicker.selectedDates[1].toISOString().split('T')[0]);
            }
        }
        // Filtro Tienda
        const storeSelect = document.getElementById('store-filter');
        if (storeSelect && storeSelect.value) {
            url.searchParams.append('store_name', storeSelect.value);
        }
        // Filtro Búsqueda
        const searchInput = document.getElementById('search-input');
        if (searchInput && searchInput.value.trim() !== "") {
            url.searchParams.append('search', searchInput.value.trim());
        }
        
        return url;
    }

    // --- 1. KPIs ---
    function updateKpis() {
        fetch(buildUrl('/api/kpi/main'))
            .then(r => r.json())
            .then(data => {
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
                
                // --- NUEVO: CANCELADOS + DINERO PERDIDO ---
                const cancelEl = document.getElementById('kpi-canceled');
                if (cancelEl) {
                    const count = data.total_canceled ?? 0;
                    const lost = (data.lost_revenue || 0).toFixed(2);
                    // Inyectamos HTML para mostrar el monto en pequeño y semitransparente
                    cancelEl.innerHTML = `${count} <span style="font-size: 0.6em; opacity: 0.8;">(-$${lost})</span>`;
                }
                // ------------------------------------------

                setVal('kpi-avg-time', `${data.avg_delivery_minutes || 0} min`);

                // Actualizar gráfico dona
                updateOrderTypeChart(data.total_deliveries, data.total_pickups);
            })
            .catch(e => console.error("Error KPIs:", e));
    }

    // --- GRÁFICO 1: DELIVERY VS PICKUP ---
    function updateOrderTypeChart(d, p) {
        const canvas = document.getElementById('orderTypeChart');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        
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
                plugins: { legend: { position: 'bottom', labels: { color: '#f8fafc' } } }
            }
        });
    }

    // --- GRÁFICO 2: CUELLOS DE BOTELLA ---
    function updateBottleneckChart() {
        fetch(buildUrl('/api/analysis/bottlenecks')).then(r => r.json()).then(data => {
            // Filtrar y Ordenar
            const filtered = data
                .filter(d => d.avg_duration_seconds > 0)
                .sort((a, b) => {
                    const idxA = statusOrder.indexOf(a.status);
                    const idxB = statusOrder.indexOf(b.status);
                    return idxA - idxB;
                });

            const ctx = document.getElementById('bottleneckChart')?.getContext('2d');
            if (!ctx) return;
            if (bottleneckChart) bottleneckChart.destroy();
            
            bottleneckChart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: filtered.map(d => statusTranslations[d.status] || d.status.toUpperCase()),
                    datasets: [{
                        label: 'Minutos',
                        data: filtered.map(d => (d.avg_duration_seconds/60).toFixed(1)),
                        backgroundColor: '#f59e0b'
                    }]
                },
                options: { indexAxis: 'y', maintainAspectRatio: false, plugins: { legend: { display: false } } }
            });
        });
    }

    // --- GRÁFICO 3: CANCELACIONES ---
    function updateCancellationChart() {
        fetch(buildUrl('/api/analysis/cancellations')).then(r => r.json()).then(data => {
            const ctx = document.getElementById('cancellationChart')?.getContext('2d');
            if(!ctx) return;
            
            let labels = [], values = [];
            if (data && data.length > 0) {
                labels = data.map(d => d.reason || 'Sin motivo');
                values = data.map(d => d.count);
            } else {
                labels = ['Sin datos']; values = [0];
            }

            if (cancellationChartInstance) cancellationChartInstance.destroy();
            
            cancellationChartInstance = new Chart(ctx, {
                type: 'pie',
                data: {
                    labels: labels,
                    datasets: [{
                        data: values,
                        backgroundColor: ['#ef4444', '#f97316', '#f59e0b', '#84cc16', '#10b981', '#06b6d4', '#3b82f6', '#6366f1', '#8b5cf6', '#d946ef'],
                        borderWidth: 0
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    layout: { padding: { right: 20 } },
                    plugins: { legend: { position: 'right', labels: { color: '#f8fafc', boxWidth: 10 } } }
                }
            });
        });
    }

    // --- GRÁFICO 4: TENDENCIAS ---
    function updateTrendsChart() {
        fetch(buildUrl('/api/data/trends')).then(r => r.json()).then(data => {
            const ctx = document.getElementById('trendsChart')?.getContext('2d');
            if(!ctx) return;
            if (trendsChart) trendsChart.destroy();
            
            trendsChart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: data.labels,
                    datasets: [
                        {
                            type: 'line', label: 'Ingresos ($)',
                            data: data.revenue, borderColor: '#10b981', backgroundColor: 'rgba(16, 185, 129, 0.1)',
                            yAxisID: 'y', fill: true, tension: 0.4
                        },
                        {
                            type: 'bar', label: 'Pedidos',
                            data: data.orders, backgroundColor: 'rgba(59, 130, 246, 0.5)', borderColor: '#3b82f6', borderWidth: 1,
                            yAxisID: 'y1'
                        },
                        {
                            type: 'line', label: 'Tiempo Prom (min)',
                            data: data.avg_times, borderColor: '#ef4444', backgroundColor: 'transparent',
                            yAxisID: 'y1', borderDash: [5,5], tension: 0.4
                        }
                    ]
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    interaction: { mode: 'index', intersect: false },
                    scales: {
                        y: { display: true, position: 'left', grid: { color: 'rgba(255,255,255,0.05)' } },
                        y1: { display: true, position: 'right', grid: { display: false } }
                    },
                    plugins: { legend: { labels: { color: '#f8fafc' } } }
                }
            });
        });
    }

    // --- GRÁFICO 5: TOP REPARTIDORES ---
    function updateDriverLeaderboard() {
        fetch(buildUrl('/api/data/driver-leaderboard')).then(r => r.json()).then(data => {
            const ctx = document.getElementById('driverLeaderboardChart')?.getContext('2d');
            if(!ctx) return;
            if (driverLeaderboardChart) driverLeaderboardChart.destroy();
            
            const bgColors = data.map(d => {
                if (d.status === 'new') return '#3b82f6';
                if (d.status === 'active') return '#10b981';
                if (d.status === 'warning') return '#f59e0b';
                return '#ef4444';
            });

            const labels = data.map(d => {
                let timeMsg = d.days_inactive === 0 ? "Hoy" : `${d.days_inactive}d`;
                return `${d.name} (${timeMsg})`;
            });

            driverLeaderboardChart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [{ label: 'Entregas', data: data.map(d => d.orders), backgroundColor: bgColors }]
                },
                options: {
                    indexAxis: 'y', maintainAspectRatio: false,
                    scales: { x: { grid: { color: 'rgba(255,255,255,0.05)' } } },
                    plugins: { 
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                afterLabel: function(context) {
                                    const item = data[context.dataIndex];
                                    return `🔥 Intensidad: ${item.daily_avg} ped/día`;
                                }
                            }
                        }
                    }
                }
            });
        });
    }

    // --- LISTA: TOP TIENDAS ---
    function updateTopStoresList() {
        fetch(buildUrl('/api/data/top-stores')).then(r => r.json()).then(data => {
            const list = document.getElementById('top-stores-list');
            if(!list) return;
            list.innerHTML = '';
            data.forEach(s => {
                list.innerHTML += `
                    <li class="list-group-item d-flex justify-content-between align-items-center px-4 py-3">
                        <div class="d-flex flex-column">
                            <span class="text-white fw-bold"><i class="fa-solid fa-store me-2 text-muted"></i>${s.name}</span>
                            <small class="text-muted ms-4" style="font-size: 0.7rem;"><i class="fa-regular fa-calendar-check me-1"></i>Desde: ${s.first_seen}</small>
                        </div>
                        <span class="badge bg-success rounded-pill">${s.orders}</span>
                    </li>`;
            });
        });
    }

    // --- TABLA: TOP CLIENTES ---
    function loadTopCustomers() {
        fetch(buildUrl('/api/data/top-customers')).then(r => r.json()).then(data => {
            const tbody = document.querySelector('#topCustomersTable tbody');
            if(!tbody) return;
            tbody.innerHTML = '';
            
            data.forEach((c) => {
                // USA EL RANK QUE VIENE DE LA API (c.rank)
                let rankDisplay = `#${c.rank}`; 
                
                // Iconos para los primeros 3 (Globales)
                if(c.rank === 1) rankDisplay = '🥇';
                if(c.rank === 2) rankDisplay = '🥈';
                if(c.rank === 3) rankDisplay = '🥉';

                tbody.innerHTML += `
                    <tr>
                        <td class="ps-4 text-warning fw-bold">${rankDisplay}</td>
                        <td class="fw-bold text-white">${c.name}</td>
                        <td class="text-center"><span class="badge bg-primary text-white">${c.count}</span></td>
                        <td class="text-end text-success fw-bold">$${c.total_amount.toFixed(2)}</td>
                        <td class="text-end pe-4 text-muted">$${(c.total_amount/c.count).toFixed(2)}</td>
                    </tr>`;
            });
            
            // Mensaje si no hay resultados
            if (data.length === 0) {
                tbody.innerHTML = `<tr><td colspan="5" class="text-center text-muted py-3">No se encontraron clientes para esta búsqueda</td></tr>`;
            }
        });
    }

    // --- TABLA: PEDIDOS RECIENTES ---
    function updateRecentOrdersTable() {
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

        fetch(buildUrl('/api/data/orders')).then(r => r.json()).then(data => {
            const tableBody = document.getElementById('recent-orders-table-body');
            if (!tableBody) return;
            
            let html = '';
            data.forEach(order => {
                // 1. Estilos de Estado
                let badgeClass = 'bg-secondary';
                if (order.current_status === 'delivered') badgeClass = 'bg-success';
                else if (order.current_status === 'canceled') badgeClass = 'bg-danger';
                else if (order.current_status === 'on_the_way') badgeClass = 'bg-info text-dark animate-pulse';
                else if (order.current_status === 'driver_assigned') badgeClass = 'bg-primary';
                
                // NUEVO ESTILO PARA SOLICITANDO
                else if (order.current_status === 'confirmed') badgeClass = 'bg-info bg-opacity-50 text-dark'; 
                
                else if (order.current_status === 'processing') badgeClass = 'bg-warning text-dark';

                // Traducción de Estado
                const statusEs = statusTranslations[order.current_status] || order.current_status;

                // 2. Lógica de Cliente + WhatsApp
                let clientHtml = `<span class="fw-bold text-white d-block" style="font-size: 0.9rem;">${order.customer_name || 'Desconocido'}</span>`;
                if (order.customer_phone) {
                    const rawPhone = order.customer_phone.replace(/\D/g, ''); // Quitar caracteres no numéricos
                    clientHtml += `
                        <a href="https://wa.me/${rawPhone}" target="_blank" class="text-success small text-decoration-none" style="font-size: 0.8rem;">
                            <i class="fa-brands fa-whatsapp me-1"></i>${order.customer_phone}
                        </a>`;
                }

                // 3. Lógica de Distancia
                let distHtml = '<span class="text-muted small">--</span>';
                if (order.distance_km && order.distance_km > 0) {
                    distHtml = `<span class="badge bg-dark border border-secondary text-info">${order.distance_km.toFixed(1)} km</span>`;
                }
                
                // 4. Lógica de Tiempos
                let timeHtml = '';
                if (order.current_status === 'delivered') {
                    timeHtml = `
                        <div class="d-flex flex-column align-items-end">
                            <span class="fw-bold text-white fs-6">${cleanDurationText(order.duration_text)}</span>
                            <small class="text-success" style="font-size:0.7rem;">COMPLETADO</small>
                        </div>`;
                } else if (order.current_status === 'canceled') {
                    timeHtml = `<span class="badge bg-danger bg-opacity-25 text-danger border border-danger">CANCELADO</span>`;
                } else {
                    timeHtml = `
                        <div class="d-flex flex-column align-items-end live-timer-container" 
                             data-created="${order.created_at}" 
                             data-state-start="${order.state_start_at}">
                            <span class="fw-bold text-white fs-5 timer-total" style="font-family: monospace;">--:--</span>
                            <small class="text-white-50" style="font-size: 0.75rem;">En estado: <span class="timer-state fw-semibold text-info">--:--</span></small>
                        </div>`;
                }

                // 5. Construcción de Fila
                html += `
                    <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                        <td class="ps-4"><span class="fw-bold text-white">#${order.external_id}</span></td>
                        
                        <!-- Columna Cliente -->
                        <td>${clientHtml}</td>
                        
                        <!-- Estado -->
                        <td><span class="badge ${badgeClass}">${statusEs.toUpperCase()}</span></td>
                        
                        <!-- Columna Distancia -->
                        <td>${distHtml}</td>
                        
                        <td class="text-white fw-bold">$${(order.total_amount||0).toFixed(2)}</td>
                        <td class="text-success fw-bold">$${(order.delivery_fee||0).toFixed(2)}</td>
                        <td class="text-end pe-4">${timeHtml}</td>
                    </tr>
                `;
            });
            tableBody.innerHTML = html;
            startLiveTimers();
        });
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
                if (!stateStr.endsWith('Z')) stateStr += 'Z'; // Fix UTC

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

    function updateHeatmap() {
        initMap();
        if(!mapInstance) return;
        const container = mapInstance.getContainer();
        if (container.clientHeight === 0) return;
        
        mapInstance.invalidateSize();
        fetch(buildUrl('/api/data/heatmap')).then(r => r.json()).then(data => {
            if (heatLayer) mapInstance.removeLayer(heatLayer);
            if (data && data.length > 0) {
                try {
                    heatLayer = L.heatLayer(data, { radius: 20, blur: 15, maxZoom: 14, max: 0.6, gradient: {0.4: 'cyan', 0.65: 'lime', 1: 'red'} }).addTo(mapInstance);
                    const bounds = data.map(p => [p[0], p[1]]);
                    if (bounds.length > 0) mapInstance.fitBounds(bounds);
                } catch(e) {}
            }
        });
        fetch('/api/data/stores-locations').then(r => r.json()).then(stores => {
            stores.forEach(s => {
                L.circleMarker([s.lat, s.lng], { radius: 6, fillColor: "#ffffff", color: "#3b82f6", weight: 2, opacity: 1, fillOpacity: 1 }).bindPopup(`<b>🏪 ${s.name}</b>`).addTo(mapInstance);
            });
        });
    }

    // --- FILTRO TIENDAS (SIN LÍMITE) ---
    function loadStoreFilterOptions() {
        fetch('/api/data/all-stores-names').then(r => r.json()).then(data => {
            const sel = document.getElementById('store-filter');
            if(!sel) return;
            const currentVal = sel.value;
            sel.innerHTML = '<option value="">Todas las Tiendas</option>';
            data.forEach(name => {
                const opt = document.createElement('option'); opt.value = name; opt.textContent = name; sel.appendChild(opt);
            });
            if (currentVal) sel.value = currentVal;
            sel.onchange = function() { fetchAllData(); };
        }).catch(e => console.error("Error tiendas", e));
    }

    // --- MAIN ---
    function fetchAllData(isSearch = false) { // <--- Parámetro opcional
        const now = new Date();
        const updateEl = document.getElementById('last-updated');
        if(updateEl) updateEl.textContent = now.toLocaleTimeString();
        
        // Efecto visual si es búsqueda
        if (isSearch) {
            document.getElementById('kpi-total-orders').textContent = '...';
            // Scroll suave al inicio
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }
        
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

    datePicker = flatpickr("#date-range-picker", { 
        mode: "range", 
        dateFormat: "Y-m-d", 
        theme: "dark", 
        defaultDate: [today, today], // <--- ESTA ES LA CLAVE
        onClose: fetchAllData 
    });

    loadStoreFilterOptions();

    // Eventos Buscador
    document.getElementById('btn-update')?.addEventListener('click', fetchAllData);
    document.getElementById('search-input')?.addEventListener('keypress', function (e) {
        if (e.key === 'Enter') fetchAllData();
    });
    
    // Limpiar búsqueda
    document.getElementById('btn-clear-search')?.addEventListener('click', function() {
        const input = document.getElementById('search-input');
        if (input) {
            input.value = ''; // Borrar texto
            fetchAllData();   // Recargar todo limpio
        }
    });

    // --- BOTÓN "TODO EL HISTORIAL" ---
    document.getElementById('btn-all-history')?.addEventListener('click', function() {
        const today = new Date();
        const startOfTime = "2025-04-25"; // Fecha arbitraria antigua para cubrir todo
        
        // Forzamos al calendario a seleccionar todo el rango
        // Esto disparará el evento 'onClose' automáticamente, que llama a fetchAllData
        datePicker.setDate([startOfTime, today]);
        
        // Feedback visual en consola
        console.log("♾️ Cargando historial completo...");
    });

    // Eventos Colapso
    document.getElementById('collapseMap')?.addEventListener('shown.bs.collapse', function () {
        if (mapInstance) setTimeout(() => { mapInstance.invalidateSize(); updateHeatmap(); }, 100);
    });

    fetchAllData();
    setInterval(fetchAllData, 60000);
});
