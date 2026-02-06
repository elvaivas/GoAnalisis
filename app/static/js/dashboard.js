document.addEventListener('DOMContentLoaded', function () {
    console.log("🚀 Dashboard V5.1 (Fixed & Stable) Cargado");

    const token = localStorage.getItem('token');
    const role = localStorage.getItem('role');

    if (!token) { window.location.href = '/login'; return; }

    if (role !== 'admin') {
        document.body.classList.add('role-viewer');
        console.log("🔒 Modo Visualizador (Datos financieros ocultos)");

        const style = document.createElement('style');
        // AÑADÍ .admin-only AQUÍ ABAJO PARA GARANTIZAR QUE SE OCULTE
        style.innerHTML = `
            #kpi-total-revenue, #kpi-total-fees, #kpi-total-coupons, 
            #kpi-driver-payout, #kpi-company-profit, #trendsChart, #heatmapContainer,
            .admin-only 
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

    // Función para descargar Excel Oficial SIN recargar y CON Token
    window.downloadOfficialExcel = async function (btn, orderId) {
        // 1. Feedback Visual (Loading)
        const originalContent = btn.innerHTML;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-2"></i>Generando...';
        btn.disabled = true;

        try {
            // 2. Petición Segura (Usa authFetch para incluir el Token)
            const res = await authFetch(`/api/data/download-legacy-excel/${orderId}`);

            if (res && res.ok) {
                // 3. Convertir respuesta a archivo descargable (Blob)
                const blob = await res.blob();
                const url = window.URL.createObjectURL(blob);

                // 4. Crear enlace fantasma y clicarlo
                const a = document.createElement('a');
                a.href = url;
                a.download = `Orden_Oficial_${orderId}.xlsx`; // Nombre del archivo
                document.body.appendChild(a);
                a.click();

                // 5. Limpieza
                window.URL.revokeObjectURL(url);
                a.remove();
            } else {
                alert("⚠️ No se pudo descargar el archivo. Verifique que el pedido exista en el sistema Legacy.");
            }
        } catch (e) {
            console.error("Error descarga:", e);
            alert("Error de conexión al intentar descargar.");
        } finally {
            // 6. Restaurar botón
            btn.innerHTML = originalContent;
            btn.disabled = false;
        }
    };

    // Variable para guardar instancias de gráficas y no duplicarlas
    let timelineCharts = {};

    window.toggleOrderDetails = async function (rowId) {
        const detailRow = document.getElementById(`detail-${rowId}`);
        const icon = document.getElementById(`icon-${rowId}`);
        const mainRow = document.getElementById(`row-${rowId}`);

        if (detailRow.classList.contains('d-none')) {
            // ABRIR
            detailRow.classList.remove('d-none');
            icon.classList.remove('fa-chevron-right');
            icon.classList.add('fa-chevron-down');
            mainRow.classList.add('table-active');

            // --- AQUÍ LA MAGIA: DIBUJAR GRÁFICA ---
            const ctx = document.getElementById(`timeline-chart-${rowId}`)?.getContext('2d');
            const loader = document.getElementById(`timeline-loading-${rowId}`);

            // Si ya existe la gráfica, no la volvemos a cargar
            if (timelineCharts[rowId]) return;

            if (ctx) {
                if (loader) loader.classList.remove('d-none'); // Mostrar loading

                try {
                    // Fetch datos del backend
                    const res = await authFetch(`/api/analysis/order/${rowId}/timeline`);
                    const data = await res.json();

                    if (loader) loader.classList.add('d-none'); // Ocultar loading

                    if (data.labels.length === 0) {
                        // No hay logs suficientes
                        return;
                    }

                    // Crear Gráfica
                    timelineCharts[rowId] = new Chart(ctx, {
                        type: 'bar',
                        data: {
                            labels: data.labels,
                            datasets: [{
                                data: data.data,
                                backgroundColor: data.colors,
                                borderRadius: 4,
                                barThickness: 20
                            }]
                        },
                        options: {
                            indexAxis: 'y', // Horizontal
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: {
                                legend: { display: false },
                                tooltip: {
                                    callbacks: { label: (c) => `${c.raw} min` }
                                },
                                datalabels: {
                                    color: '#000',
                                    anchor: 'end',
                                    align: 'right',
                                    formatter: (val) => Math.round(val) + "m",
                                    font: { weight: 'bold', size: 10 }
                                }
                            },
                            scales: {
                                x: { display: false }, // Ocultar eje X
                                y: { grid: { display: false } } // Limpiar eje Y
                            },
                            layout: { padding: { right: 30 } }
                        },
                        plugins: [ChartDataLabels] // Usamos el plugin que ya instalamos
                    });

                } catch (e) {
                    console.error("Error timeline:", e);
                    if (loader) loader.innerText = "Sin datos de tiempo";
                }
            }

        } else {
            // CERRAR
            detailRow.classList.add('d-none');
            icon.classList.remove('fa-chevron-down');
            icon.classList.add('fa-chevron-right');
            mainRow.classList.remove('table-active');
        }
    };

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

    async function authFetch(url, options = {}) { // <--- Recibe URL y Opciones
        try {
            // Combinamos los headers de autenticación con las opciones que enviamos (POST, etc)
            const defaultHeaders = {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            };

            // Mezclar headers por si enviamos otros custom
            const finalOptions = {
                ...options,
                headers: {
                    ...defaultHeaders,
                    ...(options.headers || {})
                }
            };

            const response = await fetch(url, finalOptions); // <--- Ahora sí pasa el POST

            if (response.status === 401) {
                localStorage.clear();
                window.location.href = '/login';
                return null;
            }
            return response;
        } catch (error) {
            console.error("Error en authFetch:", error);
            return null;
        }
    }

    // Helper para sacar la fecha local exacta (YYYY-MM-DD) sin conversiones locas a UTC
    function formatDateLocal(date) {
        if (!date) return '';
        const offset = date.getTimezoneOffset();
        const localDate = new Date(date.getTime() - (offset * 60 * 1000));
        return localDate.toISOString().split('T')[0];
    }

    function buildUrl(endpoint) {
        const url = new URL(window.location.origin + endpoint);

        // --- CAMBIO AQUÍ: USAR formatDateLocal ---
        if (datePicker && datePicker.selectedDates.length > 0) {
            // Usamos nuestra función segura en lugar de .toISOString() directo
            url.searchParams.append('start_date', formatDateLocal(datePicker.selectedDates[0]));

            if (datePicker.selectedDates.length > 1) {
                url.searchParams.append('end_date', formatDateLocal(datePicker.selectedDates[1]));
            } else {
                // TRUCO: Si selecciona un solo día (ej: 13 Ene), forzamos start=13 y end=13
                // Esto arregla el bug de que "no muestra nada" si solo eliges el inicio.
                url.searchParams.append('end_date', formatDateLocal(datePicker.selectedDates[0]));
            }
        }
        // ----------------------------------------

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
        if (cancelEl) cancelEl.innerHTML = `${data.total_canceled} <span class="text-danger opacity-75 small" style="font-size:0.7em;">(-$${(data.lost_revenue || 0).toFixed(2)})</span>`;
        setVal('kpi-avg-time', `${data.avg_delivery_minutes || 0} min`);
        updateOrderTypeChart(data.total_deliveries, data.total_pickups);
    }

    async function updateRecentOrdersTable() {
        const res = await authFetch(buildUrl('/api/data/orders'));
        if (!res) return;
        const data = await res.json();

        // --- CONEXIÓN VIGILANTE ---
        checkOperationalAnomalies(data);
        // --------------------------

        // Guardamos data global para el Modal ATC
        currentOrdersData = data;

        const tableBody = document.getElementById('recent-orders-table-body');
        if (!tableBody) return;

        const cleanFinalTime = (text) => {
            if (!text) return "--";
            try {
                const h = text.match(/(\d+)\s*Horas?/i)?.[1] || 0;
                const m = text.match(/(\d+)\s*Minutos?/i)?.[1] || 0;
                if (h > 0) return `${h}h ${m}m`;
                return `${m}m`;
            } catch (e) { return text; }
        };

        const calcDiff = (start, end) => {
            if (!start || !end) return "--";

            // FECHA 1 (Inicio/Creación): Viene del Scraper en Hora Local Venezuela.
            // NO le ponemos 'Z' para que el navegador sepa que es hora local.
            const d1 = new Date(start);

            // FECHA 2 (Fin/Log): Viene del Servidor en UTC.
            // SÍ le ponemos 'Z' (si falta) para que el navegador sepa que es UTC
            // y la convierta automáticamente a hora Venezuela al restar.
            const endString = end.endsWith('Z') ? end : end + 'Z';
            const d2 = new Date(endString);

            const diffMs = d2 - d1;

            // Validación: Si da negativo o muy pequeño, algo anda mal con la data
            if (isNaN(diffMs) || diffMs < 0) return "0m";

            const totalSecs = Math.floor(Math.abs(diffMs) / 1000);
            const h = Math.floor(totalSecs / 3600);
            const m = Math.floor((totalSecs % 3600) / 60);
            const s = Math.floor(totalSecs % 60); // Opcional si quieres segundos

            if (h > 0) return `${h}h ${m}m`;
            return `${m}m`;
        };

        let html = '';

        data.forEach(o => {
            // =========================================================
            // 1. DEFINICIÓN DE VARIABLES
            // =========================================================

            // =========================================================
            // A. ESTADO (PALETA DE COLORES SEMÁNTICA)
            // =========================================================
            let statusBadge = '';
            let isFinal = false;

            // Configuración Visual por Estado
            const statusConfig = {
                'pending': { color: 'secondary', icon: 'fa-clock', label: 'Pendiente' },
                'processing': { color: 'warning', icon: 'fa-file-invoice-dollar', label: 'Facturando' },
                'confirmed': { color: 'primary', icon: 'fa-tower-broadcast', label: 'Solicitando' },
                'driver_assigned': { color: 'dark', icon: 'fa-user-check', label: 'Asignado' },
                'on_the_way': { color: 'info', icon: 'fa-motorcycle', label: 'En Camino' },
                'delivered': { color: 'success', icon: 'fa-check', label: 'ENTREGADO' },
                'canceled': { color: 'danger', icon: 'fa-ban', label: 'CANCELADO' }
            };

            // Obtener config o default
            const st = statusConfig[o.current_status] || { color: 'light', icon: 'fa-question', label: o.current_status };

            // Determinamos si es estado final (para el cronómetro)
            if (o.current_status === 'delivered' || o.current_status === 'canceled') {
                isFinal = true;
            }

            // Generamos el HTML del Badge
            if (o.current_status === 'on_the_way') {
                // Estilo especial PULSE para "En Camino"
                statusBadge = `<span class="badge bg-info text-white animate-pulse shadow-sm">
                                <i class="fa-solid ${st.icon} me-1"></i>${st.label}
                               </span>`;
            } else {
                // Estilo Moderno (Fondo suave + Borde)
                // text-warning-emphasis es para que el amarillo se lea bien sobre blanco
                const textColor = st.color === 'warning' ? 'text-warning-emphasis' : `text-${st.color}`;

                statusBadge = `<span class="badge bg-${st.color} bg-opacity-10 ${textColor} border border-${st.color} border-opacity-25">
                                <i class="fa-solid ${st.icon} me-1"></i>${st.label}
                               </span>`;
            }

            // B. Lealtad (TIER BADGE)
            let tierBadge = '<span class="badge rounded-pill bg-light text-muted border" style="font-size:0.6rem">Nuevo</span>';
            const count = o.customer_orders_count || 1;
            if (count > 10) tierBadge = '<span class="badge rounded-pill bg-warning text-dark border border-warning" style="font-size:0.6rem">VIP</span>';
            else if (count > 1) tierBadge = '<span class="badge rounded-pill bg-primary bg-opacity-10 text-primary border border-primary border-opacity-25">Frecuente</span>';

            // C. Botón Resync (SOLO ADMIN)
            const userRole = localStorage.getItem('role');
            let resyncButtonHtml = '';

            if (userRole === 'admin') {
                resyncButtonHtml = `
                    <button class="btn btn-link p-0 text-muted btn-resync ms-2" 
                            onclick="event.stopPropagation(); resyncOrder('${o.external_id}', this)" 
                            title="Sincronizar datos (Solo Admin)">
                        <i class="fa-solid fa-arrows-rotate small"></i>
                    </button>
                `;
            }

            // D. Tiempo (Híbrido: Scraped o Calculado)
            let timeHtml = '';

            if (isFinal) {
                // 1. Intentamos usar el texto oficial del Legacy
                let displayTime = cleanFinalTime(o.duration_text);

                // 2. Si falla (dice "--" o vacío), lo calculamos nosotros
                if ((!displayTime || displayTime === "--" || displayTime === "") && o.state_start_at && o.created_at) {
                    // Para un pedido finalizado, state_start_at es la fecha de finalización
                    displayTime = calcDiff(o.created_at, o.state_start_at);
                }

                // Color semántico según duración (Ej: >60m en Rojo)
                // (Opcional, pero ayuda visualmente)

                timeHtml = `<div class="fw-bold text-dark fs-6">${displayTime}</div><small class="text-muted" style="font-size:0.7rem">Tiempo Total</small>`;
            } else {
                // Notar data-state-start para el cronómetro de fase
                timeHtml = `
                    <div class="live-timer-container" data-created="${o.created_at}" data-state-start="${o.state_start_at}">
                        <div class="fw-bold text-dark fs-5 timer-total font-monospace">--:--</div>
                        <small class="text-muted" style="font-size:0.65rem">En fase: <span class="timer-state text-primary fw-bold">--:--</span></small>
                    </div>`;
            }

            // E. Logística
            const typeBadge = o.order_type === 'Delivery'
                ? '<span class="badge bg-primary bg-opacity-10 text-primary mb-1"><i class="fa-solid fa-motorcycle me-1"></i>Delivery</span>'
                : '<span class="badge bg-warning bg-opacity-10 text-warning mb-1"><i class="fa-solid fa-person-walking me-1"></i>Pickup</span>';

            const driverHtml = o.driver && o.driver.name !== 'No Asignado'
                ? `<div class="d-flex align-items-center small text-dark"><i class="fa-solid fa-helmet-safety me-2 text-muted"></i>${o.driver.name}</div>`
                : `<div class="small text-muted fst-italic">--</div>`;

            // F. Items Detalle
            let itemsTable = '<div class="text-muted small fst-italic p-3">Sin productos registrados</div>';
            if (o.items && o.items.length > 0) {
                itemsTable = `
                    <table class="table table-sm table-borderless mb-0 small" style="background: transparent;">
                        <thead class="text-muted border-bottom"><tr><th>Producto</th><th class="text-center">Cant.</th><th class="text-end">Precio</th><th class="text-end">Total</th></tr></thead>
                        <tbody>
                            ${o.items.map(i => `
                                <tr>
                                    <td class="text-truncate" style="max-width: 250px;" title="${i.name}">${i.name}</td>
                                    <td class="text-center">${i.quantity}</td>
                                    <td class="text-end">$${i.unit_price.toFixed(2)}</td>
                                    <td class="text-end fw-bold">$${i.total_price.toFixed(2)}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                `;
            }

            // =========================================================
            // 2. RENDERIZADO HTML
            // =========================================================

            // FILA PRINCIPAL
            html += `
                <tr id="row-${o.id}" style="cursor: pointer; transition: background 0.2s;" onclick="toggleOrderDetails('${o.id}')">
                    <td class="ps-4">
                        <div class="d-flex align-items-center">
                            <i id="icon-${o.id}" class="fa-solid fa-chevron-right text-muted me-2 small" style="width: 15px; transition: transform 0.2s;"></i>
                            <div>
                                <div class="d-flex align-items-center">
                                    <div class="fw-bold text-dark">#${o.external_id}</div>
                                    ${resyncButtonHtml}
                                </div>
                                <span class="badge bg-light text-secondary border fw-normal" style="font-size:0.7rem">${o.store_name}</span>
                            </div>
                        </div>
                    </td>
                    <td>
                        <div class="fw-bold text-dark" style="font-size: 0.95rem;">${o.customer_name}</div>
                        <div class="d-flex align-items-center mt-1 gap-2">
                            ${tierBadge}
                            ${o.customer_phone ? `<a href="https://wa.me/${o.customer_phone.replace(/\D/g, '')}" target="_blank" onclick="event.stopPropagation()" class="text-success small text-decoration-none"><i class="fa-brands fa-whatsapp"></i></a>` : ''}
                        </div>
                    </td>
                    <td>
                        ${typeBadge}
                        ${driverHtml}
                    </td>
                    <td>
                        <div class="d-flex justify-content-between align-items-center">
                            <div class="me-3">${statusBadge}</div>
                            <div class="text-end">${timeHtml}</div>
                        </div>
                    </td>
                    <td class="text-end pe-4">
                        <div class="fw-bold text-dark fs-6">$${(o.total_amount || 0).toFixed(2)}</div>
                    </td>
                </tr>
            `;

            // FILA DETALLE
            html += `
                <tr id="detail-${o.id}" class="d-none bg-light shadow-inner">
                    <td colspan="5" class="p-0">
                        <div class="p-3 border-start border-4 border-primary">
                            <div class="row g-3">
                                <!-- COL 1: PRODUCTOS -->
                                <div class="col-md-5 border-end">
                                    <h6 class="fw-bold small text-muted mb-2 text-uppercase"><i class="fa-solid fa-pills me-2"></i>Detalle del Pedido</h6>
                                    ${itemsTable}
                                </div>
                                
                                <!-- COL 2: GRÁFICA DE TIEMPOS (NUEVO) -->
                                <div class="col-md-4 border-end d-flex flex-column">
                                    <h6 class="fw-bold small text-muted mb-2 text-uppercase"><i class="fa-solid fa-stopwatch me-2"></i>Cronología (Mins)</h6>
                                    <div style="flex-grow: 1; position: relative; min-height: 150px;">
                                        <canvas id="timeline-chart-${o.id}"></canvas>
                                        <div id="timeline-loading-${o.id}" class="text-center text-muted mt-5 small d-none">Cargando tiempos...</div>
                                    </div>
                                </div>

                                <!-- COL 3: ACCIONES -->
                                <div class="col-md-3 d-flex flex-column justify-content-center ps-4">
                                    <h6 class="fw-bold small text-muted mb-3 text-uppercase">⚡ Acciones</h6>
                                    
                                    <button onclick="event.stopPropagation(); openATCModal('${o.id}', '${o.external_id}')" 
                                            class="btn btn-primary btn-sm w-100 mb-2 text-start shadow-sm">
                                        <i class="fa-solid fa-file-invoice me-2"></i>Ficha ATC
                                    </button>

                                    <a href="https://ecosistema.gopharma.com.ve/admin/order/list/all?search=${o.external_id}" target="_blank" 
                                       onclick="event.stopPropagation()"
                                       class="btn btn-white border btn-sm w-100 text-start">
                                        <i class="fa-solid fa-external-link-alt me-2 text-muted"></i>Ver Legacy
                                    </a>
                                </div>
                            </div>
                        </div>
                    </td>
                </tr>
            `;
        });

        tableBody.innerHTML = html;
        startLiveTimers();
    }


    function startLiveTimers() {
        if (ordersInterval) clearInterval(ordersInterval);

        const formatTime = (seconds) => {
            if (seconds < 0) return "0s";
            const h = Math.floor(seconds / 3600);
            const m = Math.floor((seconds % 3600) / 60);
            const s = Math.floor(seconds % 60);
            if (h > 0) return `${h}h ${m}m ${s}s`;
            return `${m}m ${s}s`;
        };

        ordersInterval = setInterval(() => {
            const now = new Date();

            document.querySelectorAll('.live-timer-container').forEach(el => {
                // 1. TIEMPO TOTAL (Viene en Local, se usa directo)
                // data-created="2026-01-14T11:19:00" -> Navegador asume Local
                const createdDate = new Date(el.dataset.created);
                const totalSeconds = Math.floor((now - createdDate) / 1000);

                const totalEl = el.querySelector('.timer-total');
                if (totalEl) totalEl.textContent = formatTime(totalSeconds);

                // 2. TIEMPO DE FASE (Viene en UTC, forzamos conversión)
                // data-state-start="2026-01-14T15:57..." -> Es UTC, hay que decirle al navegador
                let stateStr = el.dataset.stateStart;

                if (stateStr) {
                    // TRUCO: Si no termina en 'Z', se la ponemos.
                    // Esto obliga a JS a tratarlo como UTC y restarle las 4 horas de VET
                    if (!stateStr.endsWith('Z')) stateStr += 'Z';

                    const stateStartDate = new Date(stateStr);
                    const phaseEl = el.querySelector('.timer-state');

                    if (phaseEl && !isNaN(stateStartDate)) {
                        const phaseSeconds = Math.floor((now - stateStartDate) / 1000);
                        phaseEl.textContent = formatTime(phaseSeconds);

                        // Alerta Roja > 20 min
                        if (phaseSeconds > 1200) {
                            phaseEl.classList.remove('text-primary');
                            phaseEl.classList.add('text-danger', 'fw-bold');
                        } else {
                            phaseEl.classList.remove('text-danger', 'fw-bold');
                            phaseEl.classList.add('text-primary');
                        }
                    }
                }
            });
        }, 1000);
    }

    function updateOrderTypeChart(d, p) {
        const ctx = document.getElementById('orderTypeChart')?.getContext('2d');
        if (!ctx) return;
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
            const localStatusOrder = [
                'created', 'pending', 'processing', 'confirmed', 'driver_assigned', 'on_the_way',
                'delivered', 'canceled'
            ];

            const localTranslations = {
                'created': 'Creado',
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

                const sorted = list
                    .filter(d => d.avg_duration_seconds > 0)
                    .sort((a, b) => localStatusOrder.indexOf(a.status) - localStatusOrder.indexOf(b.status));

                const labels = sorted.map(d => localTranslations[d.status] || d.status);
                // Convertimos a minutos con 1 decimal
                const values = sorted.map(d => (d.avg_duration_seconds / 60).toFixed(1));

                const colors = sorted.map(d => {
                    if (d.status === 'canceled') return '#ef4444';
                    if (d.status === 'delivered') return '#10b981';
                    if (d.status === 'on_the_way') return '#0dcaf0'; // Info
                    if (d.status === 'processing') return '#ffc107'; // Warning
                    return ctxPickup ? '#3b82f6' : '#f59e0b';
                });

                return { labels, values, colors };
            };

            // CONFIGURACIÓN COMÚN (DATALABELS)
            const chartOptions = {
                indexAxis: 'y',
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    // AQUÍ ESTÁ LA MAGIA DE LOS NÚMEROS
                    datalabels: {
                        anchor: 'end', // Al final de la barra
                        align: 'end',  // Por fuera (a la derecha)
                        color: '#4b5563',
                        font: { weight: 'bold', size: 11 },
                        formatter: function (value) {
                            return value + ' m'; // Ej: "15.2 m"
                        }
                    }
                },
                scales: {
                    x: { display: false, max: undefined }, // Dejar que se autoajuste para que quepan los números
                    y: { grid: { display: false } }
                },
                layout: {
                    padding: { right: 40 } // Espacio extra a la derecha para que no se corte el texto
                }
            };

            // 2. RENDER DELIVERY
            if (ctxDelivery) {
                const dData = processData(data.delivery);

                // Si ya existe, destruirlo para limpiar plugins viejos
                if (bottleneckChart) bottleneckChart.destroy();

                // ACTIVAR PLUGIN
                Chart.register(ChartDataLabels);

                bottleneckChart = new Chart(ctxDelivery, {
                    type: 'bar',
                    data: {
                        labels: dData.labels,
                        datasets: [{
                            label: 'Minutos',
                            data: dData.values,
                            backgroundColor: dData.colors,
                            borderRadius: 4,
                            barPercentage: 0.6
                        }]
                    },
                    options: chartOptions
                });
            }

            // 3. RENDER PICKUP
            if (ctxPickup) {
                const pData = processData(data.pickup);

                if (bottleneckPickupChart) bottleneckPickupChart.destroy();

                bottleneckPickupChart = new Chart(ctxPickup, {
                    type: 'bar',
                    data: {
                        labels: pData.labels,
                        datasets: [{
                            label: 'Minutos',
                            data: pData.values,
                            backgroundColor: pData.colors,
                            borderRadius: 4,
                            barPercentage: 0.6
                        }]
                    },
                    options: chartOptions
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
            let rank = `#${c.rank}`; if (c.rank === 1) rank = '🥇'; if (c.rank === 2) rank = '🥈'; if (c.rank === 3) rank = '🥉';
            tbody.innerHTML += `<tr><td class="ps-4 fw-bold text-warning">${rank}</td><td class="fw-bold">${c.name}</td><td class="text-center"><span class="badge bg-primary">${c.count}</span></td><td class="text-end fw-bold text-success">$${c.total_amount.toFixed(2)}</td><td class="text-end pe-4 text-muted">$${(c.total_amount / c.count).toFixed(2)}</td></tr>`;
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
            let icon = i === 0 ? '🥇' : (i === 1 ? '🥈' : (i === 2 ? '🥉' : '📦'));
            tbody.innerHTML += `<tr><td class="ps-4"><span>${icon}</span> <b>${p.name}</b></td><td class="text-center"><span class="badge bg-soft-primary text-primary border">${p.quantity}</span></td><td class="text-end pe-4 text-success fw-bold">$${p.revenue.toFixed(2)}</td></tr>`;
        });
    }

    // --- 4. TENDENCIAS (Gráfico Mixto: $ + Pedidos + Tiempo) ---
    async function updateTrendsChart() {
        const ctx = document.getElementById('trendsChart')?.getContext('2d');
        if (!ctx) return;

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
                        borderDash: [5, 5],
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
        if (!ctx) return;

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
        if (!list) return;

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

    // --- 7. MAPA DE CALOR (Leaflet - BLINDADO) ---
    async function updateHeatmap() {
        const mapDiv = document.getElementById('heatmapContainer');
        if (!mapDiv) return;

        // 1. Obtener Datos (Siempre, para tenerlos listos)
        const res = await authFetch(buildUrl('/api/data/heatmap'));
        if (!res) return;
        const data = await res.json();

        // 2. CHECK DE SEGURIDAD (Si está oculto/colapsado)
        if (mapDiv.clientHeight === 0 || mapDiv.clientWidth === 0) {
            console.warn("⚠️ Mapa oculto: Limpiando capas para evitar crash.");

            // CRÍTICO: Si el mapa está oculto, QUITAMOS la capa de calor para que no intente
            // dibujarse en un canvas de 0px y genere el error IndexSizeError.
            if (mapInstance && heatLayer) {
                mapInstance.removeLayer(heatLayer);
                heatLayer = null;
            }
            return;
        }

        // 3. Inicialización única (Si es visible y no existe el mapa)
        if (!mapInstance) {
            mapInstance = L.map('heatmapContainer').setView([10.4806, -66.9036], 12);
            L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
                maxZoom: 19,
                attribution: '&copy; OpenStreetMap'
            }).addTo(mapInstance);
        }

        // 4. Forzar ajuste de tamaño (Vital cuando se abre el acordeón)
        mapInstance.invalidateSize();

        // 5. Limpieza de capa anterior (Si existía)
        if (heatLayer) {
            mapInstance.removeLayer(heatLayer);
            heatLayer = null;
        }

        // 6. Pintar Nueva Capa
        if (data && data.length > 0) {
            try {
                heatLayer = L.heatLayer(data, {
                    radius: 20,
                    blur: 15,
                    maxZoom: 14,
                    minOpacity: 0.4,
                    gradient: { 0.4: 'cyan', 0.65: 'lime', 1: 'red' }
                }).addTo(mapInstance);

                // Auto-ajustar zoom para ver los puntos
                if (data.length > 1) {
                    const bounds = data.map(p => [p[0], p[1]]);
                    mapInstance.fitBounds(bounds, { padding: [20, 20] });
                }
            } catch (e) {
                console.error("Error pintando heatmap:", e);
            }
        }

        // 7. Cargar Tiendas (Puntos Azules)
        try {
            const resStores = await authFetch('/api/data/stores-locations');
            if (resStores) {
                const stores = await resStores.json();
                stores.forEach(s => {
                    // Usamos un ID único para no duplicar marcadores si ya existen (opcional, Leaflet maneja esto bien)
                    L.circleMarker([s.lat, s.lng], {
                        radius: 5, fillColor: "#fff", color: "#3b82f6", weight: 2, fillOpacity: 1
                    }).bindPopup(`<b>${s.name}</b>`).addTo(mapInstance);
                });
            }
        } catch (e) { }
    }

    // --- 8. FILTRO DE TIENDAS (Dropdown) ---
    async function loadStoreFilterOptions() {
        const sel = document.getElementById('store-filter');
        if (!sel) return;

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
        sel.onchange = function () {
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
        const timeString = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
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
    // --- NUEVO LISTENER PARA BOTÓN HOY ---
    document.getElementById('btn-today')?.addEventListener('click', () => {
        const today = new Date();
        // Seteamos Hoy como Inicio y Fin
        datePicker.setDate([today, today]);
        fetchAllData();
    });
    // -------------------------------------

    loadStoreFilterOptions();

    fetchAllData();
    setInterval(fetchAllData, 60000);
    // --- FUNCIÓN RESYNC MANUAL ---
    window.resyncOrder = async function (externalId, btnElement) {
        // 1. Efecto Visual de Carga (Spinning)
        const icon = btnElement.querySelector('i');
        icon.classList.add('fa-spin', 'text-primary');
        btnElement.disabled = true;

        try {
            // 2. Llamada al Backend
            const res = await authFetch(`/api/data/orders/${externalId}/resync`, {
                method: 'POST' // Es una acción, usamos POST
            });

            if (res && res.ok) {
                // 3. Éxito: Feedback y Recarga suave
                icon.classList.remove('text-primary');
                icon.classList.add('text-success');

                // Pequeña pausa para que el usuario vea el verde
                setTimeout(() => {
                    fetchAllData(); // Recargamos la tabla para ver los cambios
                }, 500);
            } else {
                alert("Error al sincronizar. Revise los logs.");
                icon.classList.remove('fa-spin', 'text-primary');
                icon.classList.add('text-danger');
                btnElement.disabled = false;
            }
        } catch (e) {
            console.error(e);
            alert("Error de conexión.");
            icon.classList.remove('fa-spin');
            btnElement.disabled = false;
        }
    };

    // --- FUNCIÓN AUDITORÍA ATC (V4 - INTEGRADA Y BLINDADA) ---
    window.openATCModal = async function (dbId, externalId) {
        const modalEl = document.getElementById('modalATC');
        if (!modalEl) return;
        const modalBody = document.getElementById('modalATCBody');
        const modal = new bootstrap.Modal(modalEl);

        modalBody.innerHTML = `
            <div class="text-center py-5">
                <div class="spinner-border text-primary" role="status"></div>
                <h5 class="mt-3 fw-bold">Generando Ficha Técnica...</h5>
                <p class="text-muted">Sincronizando Legacy + Base de Datos Local...</p>
            </div>
        `;
        modal.show();

        try {
            // 1. PETICIÓN DE DATOS
            const res = await authFetch(`/api/data/live-audit/${externalId}`);
            if (!res || !res.ok) throw new Error("Error conectando con API de Auditoría.");

            const responseJson = await res.json();
            const data = responseJson.legacy; // Datos del CSV (La Verdad)
            const items = responseJson.items || []; // Productos (DB Local)

            if (!data) throw new Error("El archivo CSV del Legacy llegó vacío.");

            // 2. CONFIGURACIÓN VISUAL
            const originalTitle = document.title;
            const cleanName = (data['Nombre del cliente'] || 'Cliente').replace(/[\\/:*?"<>|]/g, '');
            document.title = `Ficha #${data['ID del pedido']} - ${cleanName}`;

            modalEl.addEventListener('hidden.bs.modal', () => { document.title = originalTitle; }, { once: true });

            // 3. PARSER INTELIGENTE (USA / VED)
            const parseM = (val) => {
                if (!val) return 0.00;
                if (typeof val === 'number') return val;
                let v = String(val).trim();

                // Detección automática de formato
                // Caso VED: "1.500,50" (Coma al final)
                if (v.includes(',') && (v.lastIndexOf(',') > v.lastIndexOf('.'))) {
                    v = v.replace(/\./g, '').replace(',', '.');
                }
                // Caso USA: "1,500.50" (Punto al final)
                else if (v.includes('.') && (v.lastIndexOf('.') > v.lastIndexOf(','))) {
                    v = v.replace(/,/g, '');
                }
                return parseFloat(v) || 0.00;
            };

            const fmt = (n, symbol = "$") => {
                return `${symbol}${n.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
            };

            // 4. EXTRACCIÓN DE TASA
            let exchangeRate = 0;
            const tasaStr = data['Tasa de cambio'] || "";
            // Regex que busca "VED 123.45" o "= 123.45"
            const match = tasaStr.match(/VED\s*([\d.,]+)/i) || tasaStr.match(/=\s*([\d.,]+)/);
            if (match) exchangeRate = parseM(match[1]);

            console.log(`📊 Debug: Items=${items.length}, Tasa=${exchangeRate}, StringTasa="${tasaStr}"`);

            // 5. CÁLCULO DE TABLA DETALLADA (EL CEREBRO)
            let productsHtml = '';

            if (items.length > 0 && exchangeRate > 0) {
                // --- ALGORITMO DETECTIVE DE IVA ---
                const IVA_RATE = 0.16;
                const totalDbNetUsd = items.reduce((acc, item) => acc + (item.unit_price * item.quantity), 0);
                const legacyTaxUsd = parseM(data['Impuesto (USD)']);

                let itemTaxMap = new Array(items.length).fill(0);
                let methodUsed = "proportional"; // Por defecto seguro

                // Lógica de detección
                if (legacyTaxUsd === 0) {
                    methodUsed = "none"; // Todo exento
                } else if (Math.abs(legacyTaxUsd - (totalDbNetUsd * IVA_RATE)) < 0.05) {
                    itemTaxMap.fill(1);
                    methodUsed = "all"; // Todo gravado
                } else if (items.length <= 20) {
                    // Detective Subset Sum (Solo si hay pocos items)
                    const targetBase = legacyTaxUsd / IVA_RATE;
                    const findSubset = (idx, currentSum, selection) => {
                        if (Math.abs(currentSum - targetBase) < 0.03) return selection;
                        if (idx >= items.length || currentSum > targetBase + 0.03) return null;

                        // Con item
                        const v = items[idx].unit_price * items[idx].quantity;
                        const r1 = findSubset(idx + 1, currentSum + v, [...selection, idx]);
                        if (r1) return r1;
                        // Sin item
                        return findSubset(idx + 1, currentSum, selection);
                    };

                    const res = findSubset(0, 0, []);
                    if (res) {
                        res.forEach(i => itemTaxMap[i] = 1);
                        methodUsed = "exact";
                    }
                }

                // Fallback proporcional
                let taxMultiplierFallback = 1;
                if (totalDbNetUsd > 0) taxMultiplierFallback = 1 + (legacyTaxUsd / totalDbNetUsd);

                // --- ARMADO DE HTML ---
                productsHtml = `
                    <div class="mt-4 mb-3">
                        <div class="d-flex align-items-center mb-2">
                            <i class="fa-solid fa-calculator text-primary me-2"></i>
                            <div>
                                <h6 class="fw-bold text-dark mb-0">CÁLCULO UNITARIO (Para Devoluciones)</h6>
                                <small class="text-muted" style="font-size: 0.7rem;">
                                    ${methodUsed === 'exact' ? 'IVA identificado por producto' : methodUsed === 'proportional' ? 'IVA prorrateado (estimado)' : 'Cálculo directo'}
                                </small>
                            </div>
                        </div>
                        <div class="table-responsive border rounded-3">
                            <table class="table table-striped table-hover mb-0 align-middle small">
                                <thead class="bg-light text-secondary">
                                    <tr>
                                        <th class="ps-3 py-2">PRODUCTO</th>
                                        <th class="text-center py-2">CANT.</th>
                                        <th class="text-end py-2">UNIT ($)</th>
                                        <th class="text-end py-2 bg-soft-success text-success fw-bold border-start">REEMBOLSO (Bs)</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${items.map((item, idx) => {
                    let multiplier = 1;
                    let badge = '';

                    // --- REGLA MAESTRA DEL CERO ---
                    if (item.unit_price === 0) {
                        multiplier = 1; // El cero se queda quieto
                        badge = '<span class="badge bg-light text-secondary border ms-1" style="font-size:0.6em">Obsequio</span>';
                    }
                    // --- LÓGICA DE IMPUESTOS NORMAL ---
                    else if (methodUsed === 'exact' || methodUsed === 'all') {
                        if (itemTaxMap[idx] === 1) {
                            multiplier = 1.16;
                            badge = '<span class="badge bg-secondary ms-1" style="font-size:0.6em">+IVA</span>';
                        }
                    } else if (methodUsed === 'proportional') {
                        multiplier = taxMultiplierFallback;
                    }

                    const grossUsd = item.unit_price * multiplier;
                    const grossBs = grossUsd * exchangeRate;

                    return `
                                        <tr>
                                            <td class="ps-3 text-truncate" style="max-width: 250px;">${item.name}</td>
                                            <td class="text-center fw-bold">${item.quantity}</td>
                                            <td class="text-end text-muted">${fmt(item.unit_price)}${badge}</td>
                                            <td class="text-end fw-bold text-success bg-soft-success border-start fs-6">
                                                ${fmt(grossBs, 'Bs.')}
                                            </td>
                                        </tr>`;
                }).join('')}
                                </tbody>
                            </table>
                            <div class="bg-light p-1 px-3 text-end text-muted fst-italic" style="font-size: 0.75rem;">
                                Tasa Ref: 1 USD = ${fmt(exchangeRate, 'Bs.')}
                            </div>
                        </div>
                    </div>
                `;
            } else {
                // MENSAJE DE ERROR AMIGABLE SI FALLA LA TABLA
                let errorMsg = "No se pudo generar el cálculo detallado.";
                if (items.length === 0) errorMsg = "⚠️ No hay productos registrados en la base de datos local para este pedido.";
                else if (exchangeRate === 0) errorMsg = "⚠️ No se pudo leer la Tasa de Cambio del archivo Legacy.";

                productsHtml = `<div class="alert alert-warning mt-3 small">${errorMsg}</div>`;
            }

            // 6. PLANTILLA FINAL
            const html = `
                <style>
                    @media print {
                        @page { margin: 15mm; size: auto; }
                        body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
                        .modal-footer, .btn-close { display: none !important; }
                        .card { border: 1px solid #ddd !important; }
                        a { text-decoration: none !important; color: black !important; }
                    }
                </style>

                <div class="d-flex justify-content-between align-items-start mb-4 border-bottom pb-3">
                    <div>
                        <div class="text-primary fw-bold small mb-1"><i class="fa-solid fa-shield-halved me-1"></i>DATOS OFICIALES DEL LEGACY</div>
                        <h1 class="fw-bold mb-0 text-dark display-6">#${data['ID del pedido']}</h1>
                        <div class="text-muted">${data['Nombre de la tienda']}</div>
                    </div>
                    <div class="text-end">
                        <div class="small text-muted text-uppercase fw-bold">FECHA OFICIAL</div>
                        <div class="fs-5 text-dark mb-2">${data['Fecha']}</div>
                        <span class="badge bg-${data['Estado del pedido'] === 'Entregado' ? 'success' : 'dark'} fs-6 border">
                            ${data['Estado del pedido']}
                        </span>
                    </div>
                </div>

                <div class="row g-4 mb-4">
                    <div class="col-6">
                        <div class="p-3 border rounded h-100">
                            <h6 class="text-primary fw-bold mb-3"><i class="fa-solid fa-user me-2"></i>CLIENTE</h6>
                            <table class="table table-borderless table-sm mb-0 small">
                                <tr><td class="text-muted ps-0">Nombre:</td><td class="fw-bold text-end">${data['Nombre del cliente']}</td></tr>
                                <tr><td class="text-muted ps-0">Email:</td><td class="text-end text-break">${data['Correo electrónico del cliente']}</td></tr>
                                <tr><td class="text-muted ps-0">Teléfono:</td><td class="text-end fw-bold">${data['Teléfono del cliente']}</td></tr>
                            </table>
                        </div>
                    </div>
                    <div class="col-6">
                        <div class="p-3 border rounded h-100">
                            <h6 class="text-success fw-bold mb-3"><i class="fa-solid fa-money-check-dollar me-2"></i>PAGO</h6>
                            <table class="table table-borderless table-sm mb-0 small">
                                <tr><td class="text-muted ps-0">Método:</td><td class="text-end fw-bold">${data['Método de pago']}</td></tr>
                                <tr><td class="text-muted ps-0">Referencia:</td><td class="text-end fw-bold text-primary">${data['Referencia']}</td></tr>
                                <tr><td class="text-muted ps-0">Estado:</td><td class="text-end text-success fw-bold">${data['Estado del pago']}</td></tr>
                                <tr><td class="text-muted ps-0">Tasa:</td><td class="text-end">${data['Tasa de cambio']}</td></tr>
                            </table>
                        </div>
                    </div>
                </div>

                <!-- AQUÍ SE INYECTA LA TABLA DE PRODUCTOS -->
                ${productsHtml}

                <h6 class="fw-bold text-dark ps-1 mb-2 mt-4"><i class="fa-solid fa-receipt me-2"></i>DESGLOSE FINAL (LEGACY)</h6>
                <div class="table-responsive border rounded mb-3">
                    <table class="table table-bordered mb-0 small">
                        <thead class="bg-light text-center text-uppercase text-secondary">
                            <tr><th>Concepto</th><th>USD ($)</th><th>VED (Bs)</th></tr>
                        </thead>
                        <tbody>
                            <tr><td class="ps-3">Subtotal Artículos</td><td class="text-end pe-3">${fmt(parseM(data['Precio del artículo (USD)']))}</td><td class="text-end pe-3">${fmt(parseM(data['Precio del artículo (VED)']), 'Bs.')}</td></tr>
                            <tr><td class="ps-3">Descuentos</td><td class="text-end pe-3 text-danger">-${fmt(parseM(data['Monto descontado (USD)']))}</td><td class="text-end pe-3 text-danger">-${fmt(parseM(data['Monto descontado (VED)']), 'Bs.')}</td></tr>
                            <tr><td class="ps-3">Impuestos</td><td class="text-end pe-3">${fmt(parseM(data['Impuesto (USD)']))}</td><td class="text-end pe-3">${fmt(parseM(data['Impuesto (VED)']), 'Bs.')}</td></tr>
                            <tr><td class="ps-3 text-muted">Delivery Fee</td><td class="text-end pe-3 text-muted">${fmt(parseM(data['Cargo de entrega (USD)']))}</td><td class="text-end pe-3 text-muted">${fmt(parseM(data['Cargo de entrega (VED)']), 'Bs.')}</td></tr>
                            <tr><td class="ps-3 text-muted">Service Fee</td><td class="text-end pe-3 text-muted">${fmt(parseM(data['Tarifa de servicio (USD)']))}</td><td class="text-end pe-3 text-muted">${fmt(parseM(data['Tarifa de servicio (VED)']), 'Bs.')}</td></tr>
                        </tbody>
                        <tfoot class="bg-dark text-white">
                            <tr>
                                <td class="ps-3 fw-bold text-end">TOTAL COBRADO:</td>
                                <td class="text-end pe-3 fw-bold fs-6">${fmt(parseM(data['Monto total (USD)']))}</td>
                                <td class="text-end pe-3 fw-bold fs-6">${fmt(parseM(data['Monto total (VED)']), 'Bs.')}</td>
                            </tr>
                        </tfoot>
                    </table>
                </div>

                <div class="alert alert-warning small d-flex align-items-start py-2">
                    <i class="fa-solid fa-triangle-exclamation mt-1 me-2"></i>
                    <div><strong>Nota:</strong> Service Fee y Delivery Fee no suelen ser reembolsables.</div>
                </div>
            `;

            modalBody.innerHTML = html;

        } catch (e) {
            console.error(e);
            modalBody.innerHTML = `<div class="text-center py-5 text-danger"><h5>Error</h5><p>${e.message}</p></div>`;
        }
    };
    // =========================================================
    // 🔔 MÓDULO VIGILANTE V2 (PERSISTENTE Y ROBUSTO)
    // =========================================================

    // Leemos preferencia guardada (o false por defecto)
    let notificationsEnabled = localStorage.getItem('vigilante_active') === 'true';
    let ordersMemory = {};
    let isFirstLoad = true;

    const soundNewOrder = new Audio("https://actions.google.com/sounds/v1/alarms/beep_short.ogg");
    const soundAlert = new Audio("https://actions.google.com/sounds/v1/alarms/bugle_tune.ogg");

    const btnNotif = document.getElementById('btn-notifications');
    const badgeNotif = document.getElementById('notif-badge');

    // 1. INICIALIZACIÓN VISUAL (Al cargar página)
    function initVigilante() {
        if (!btnNotif) {
            console.warn("⚠️ No se encontró el botón #btn-notifications en el HTML.");
            return;
        }

        // Si el usuario lo dejó activo, verificamos que el navegador aún tenga permiso
        if (notificationsEnabled && Notification.permission === "granted") {
            updateNotifIcon(true);
            console.log("🔔 Vigilante: Restaurado (ACTIVO)");
        } else {
            notificationsEnabled = false;
            updateNotifIcon(false);
            console.log("🔕 Vigilante: Inactivo");
        }
    }

    // 2. GESTIÓN DEL BOTÓN
    btnNotif?.addEventListener('click', () => {
        console.log("👆 Click en Campana. Permiso:", Notification.permission);

        const isSecure = window.isSecureContext;

        if (!notificationsEnabled) {
            // A. YA TIENE PERMISO -> ACTIVAR
            if (Notification.permission === "granted") {
                toggleVigilante(true);
            }
            // B. BLOQUEADO O NO SEGURO -> MOSTRAR AYUDA INTELIGENTE
            else if (Notification.permission === "denied" || !isSecure) {

                // 1. Detectar Navegador para dar la URL correcta
                const userAgent = navigator.userAgent.toLowerCase();
                let flagsUrl = "chrome://flags/#unsafely-treat-insecure-origin-as-secure"; // Default (Chrome/Brave)

                if (userAgent.indexOf("edg") > -1) {
                    flagsUrl = "edge://flags/#unsafely-treat-insecure-origin-as-secure"; // Microsoft Edge
                } else if (userAgent.indexOf("opera") > -1 || userAgent.indexOf("opr") > -1) {
                    flagsUrl = "opera://flags/#unsafely-treat-insecure-origin-as-secure"; // Opera
                }

                // 2. Rellenar los inputs del Modal
                const inputFlag = document.getElementById('inputFlagUrl');
                const inputIp = document.getElementById('inputServerUrl');

                if (inputFlag) inputFlag.value = flagsUrl;
                if (inputIp) inputIp.value = window.location.origin; // IP Automática (ej: http://10.10.100.58:8001)

                // 3. Mostrar Modal
                const helpModal = new bootstrap.Modal(document.getElementById('modalNotifHelp'));
                helpModal.show();
            }
            // C. PRIMERA VEZ -> PEDIR PERMISO
            else {
                Notification.requestPermission().then(permission => {
                    if (permission === "granted") {
                        toggleVigilante(true);
                    } else {
                        // Si niega, la próxima vez caerá en el Caso B
                        console.warn("Usuario denegó permiso.");
                    }
                });
            }
        } else {
            toggleVigilante(false);
        }
    });

    function toggleVigilante(state) {
        notificationsEnabled = state;
        localStorage.setItem('vigilante_active', state); // Guardar preferencia
        updateNotifIcon(state);

        if (state) {
            // Sonido de confirmación
            soundNewOrder.volume = 0.5;
            soundNewOrder.play().catch(e => console.warn("Audio bloqueado:", e));

            // Notificación de prueba
            new Notification("GoAnalisis Vigilante", {
                body: "✅ Monitoreo en segundo plano activado.",
                icon: "/static/img/logo.png"
            });
        }
    }

    function updateNotifIcon(isActive) {
        const icon = btnNotif.querySelector('i');
        if (isActive) {
            // ESTADO ACTIVO
            btnNotif.classList.remove('btn-outline-secondary');
            btnNotif.classList.add('btn-primary', 'shadow', 'pulse-animation');
            icon.className = 'fa-solid fa-bell';
            badgeNotif.classList.remove('d-none');
        } else {
            // ESTADO INACTIVO
            btnNotif.classList.add('btn-outline-secondary');
            btnNotif.classList.remove('btn-primary', 'shadow', 'pulse-animation');
            icon.className = 'fa-regular fa-bell-slash';
            badgeNotif.classList.add('d-none');
        }
    }

    // 3. FUNCIÓN DE DISPARO
    function sendNotification(title, body, type = 'info') {
        if (!notificationsEnabled) return;

        // Visual
        const notif = new Notification(title, {
            body: body,
            icon: '/static/img/logo.png',
            requireInteraction: type === 'alert',
            tag: title
        });

        notif.onclick = () => { window.focus(); notif.close(); };

        // Audio
        try {
            if (type === 'alert') {
                soundAlert.currentTime = 0;
                soundAlert.volume = 1.0;
                soundAlert.play();
            } else {
                soundNewOrder.currentTime = 0;
                soundNewOrder.volume = 0.5;
                soundNewOrder.play();
            }
        } catch (e) { console.warn("Audio error:", e); }
    }

    // 4. LÓGICA DE DETECCIÓN (EL CEREBRO)
    function checkOperationalAnomalies(newOrders) {
        const LIMITS = { 'pending': 10, 'processing': 15, 'confirmed': 15, 'driver_assigned': 15, 'on_the_way': 45 };
        const currentIds = new Set();

        // --- DEFINIR EL INICIO DEL DÍA (00:00 AM) ---
        const today = new Date();
        today.setHours(0, 0, 0, 0); // Resetear a medianoche local
        const todayTime = today.getTime();

        newOrders.forEach(o => {
            // --- FILTRO ANTI-SPAM (SEGURIDAD) ---
            // Convertimos la fecha del pedido a objeto Date
            const orderDate = new Date(o.created_at);

            // Si el pedido es más viejo que hoy a las 00:00, LO IGNORAMOS.
            if (orderDate.getTime() < todayTime) {
                return; // Salta a la siguiente iteración sin notificar
            }
            // ------------------------------------

            currentIds.add(o.id);
            const prev = ordersMemory[o.id];

            // A. NUEVO PEDIDO
            if (!prev) {
                if (!isFirstLoad) {
                    sendNotification(`💰 Nuevo Pedido #${o.external_id}`, `${o.customer_name} ($${o.total_amount})`, 'info');
                }
            }
            // B. CAMBIO DE ESTADO
            else if (prev.status !== o.current_status) {
                const mapStatus = {
                    'processing': '🟡 Facturando',
                    'confirmed': '🔵 Solicitando',
                    'driver_assigned': '⚫ Motorizado Asignado',
                    'on_the_way': '💠 En Camino',
                    'delivered': '✅ Entregado',
                    'canceled': '🔴 Cancelado'
                };
                if (mapStatus[o.current_status]) {
                    sendNotification(`Actualización #${o.external_id}`, `Ahora está: ${mapStatus[o.current_status]}`, 'info');
                }
            }

            // C. RETRASOS
            if (o.state_start_at && LIMITS[o.current_status]) {
                let stateStr = o.state_start_at;
                if (!stateStr.endsWith('Z')) stateStr += 'Z';

                const elapsedMinutes = (new Date() - new Date(stateStr)) / 1000 / 60;
                const keyAlert = `alerted_${o.current_status}`;

                const prevFlags = prev || {};

                if (elapsedMinutes > LIMITS[o.current_status] && !prevFlags[keyAlert]) {
                    sendNotification(
                        `⚠️ DEMORA CRÍTICA #${o.external_id}`,
                        `${Math.floor(elapsedMinutes)} min en ${o.current_status.toUpperCase()}`,
                        'alert'
                    );
                    if (!ordersMemory[o.id]) ordersMemory[o.id] = {};
                    ordersMemory[o.id][keyAlert] = true;
                }
            }

            const existing = ordersMemory[o.id] || {};
            ordersMemory[o.id] = { ...existing, status: o.current_status, time: new Date() };
        });
        isFirstLoad = false;
    }

    // Inicializar al cargar
    initVigilante();

}); // <--- FINAL DEL ARCHIVO (ASEGÚRATE DE QUE ESTÉ)
