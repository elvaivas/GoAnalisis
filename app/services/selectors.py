from selenium.webdriver.common.by import By

LOGIN_SELECTORS = {
    # Actualizado al nuevo panel: usa IDs en lugar de NAME
    "email_input": (By.ID, "signinSrEmail"),
    "password_input": (By.ID, "signupSrPassword"),
    "login_button": (By.XPATH, "//button[@type='submit']"),
    "dashboard_indicator": (
        By.CSS_SELECTOR,
        "a[href='https://app.gopharma.dev/admin/order/list/all']",
    ),
}

ORDER_TABLE_SELECTORS = {
    "table_body": (By.ID, "set-rows"),
    "order_id_link": (By.CSS_SELECTOR, "td.table-column-pl-0 a"),
    # --- NUEVOS SELECTORES DE LISTADO Y EXPORTACIÓN ---
    "search_input": (By.ID, "filter-search"),  # Actualizado al nuevo modal de filtros
    "export_dropdown_btn": (
        By.CSS_SELECTOR,
        "a[data-hs-unfold-target='#usersExportDropdown']",
    ),
    "csv_export_btn": (
        By.XPATH,
        "//a[contains(@id, 'export-csv') or contains(text(), 'CSV')]",
    ),
    "order_rows": (
        By.CSS_SELECTOR,
        "table#datatable tbody tr[class*='status-']:not(.group)",
    ),
    "duration_cell": (By.CSS_SELECTOR, "td:nth-child(2)"),
    "next_page_btn": (By.CSS_SELECTOR, "a.page-link[rel='next']"),
}

ORDER_DETAIL_SELECTORS = {
    # Buscamos el bloque completo de "Status" y obtenemos el valor del segundo elemento
    "status_badge": (
        By.XPATH,
        "//div[contains(@class, 'ant-space-horizontal') and contains(., 'Status:')]/div[2]/span",
    ),
    "order_placed_at": (
        By.XPATH,
        "//span[@aria-label='calendar']/ancestor::div[contains(@class, 'ant-space-item')]/following-sibling::div[1]/span",
    ),
    "order_type_label": (
        By.XPATH,
        "//div[contains(@class, 'ant-space-horizontal') and contains(., 'Order type:')]/div[2]/span",
    ),
    "payment_method": (
        By.XPATH,
        "//div[contains(@class, 'ant-space-horizontal') and contains(., 'Payment method:')]/div[2]/span",
    ),
    # Para los otros, usa estos que son más estables:
    "customer_name": (By.XPATH, "//div[contains(@class, 'ant-card-head-title') and contains(text(), 'Customer info')]/ancestor::div[contains(@class, 'ant-card')]//h5"),
    "driver_name": (By.XPATH, "//div[contains(@class, 'ant-card-head-title') and contains(text(), 'Delivery man')]/ancestor::div[contains(@class, 'ant-card')]//h5"),
    "store_name": (By.XPATH, "//div[contains(@class, 'ant-card-head-title') and contains(text(), 'Store info')]/ancestor::div[contains(@class, 'ant-card')]//h5"),
    "customer_name": (
        By.XPATH,
        "//div[contains(@class, 'ant-card-head-title') and contains(text(), 'Customer info')]/ancestor::div[contains(@class, 'ant-card')]//h5",
    ),
    "driver_name": (
        By.XPATH,
        "//div[contains(@class, 'ant-card-head-title') and contains(text(), 'Delivery man')]/ancestor::div[contains(@class, 'ant-card')]//h5",
    ),
    # --- MONTOS (Actualizado a Componente ant-descriptions) ---
    "delivery_fee": (
        By.XPATH,
        "//th[contains(@class, 'ant-descriptions-item-label') and (contains(., 'Delivery charge') or contains(., 'Tarifa de entrega'))]/following-sibling::td[contains(@class, 'ant-descriptions-item-content')]/span",
    ),
    "total_amount": (
        By.XPATH,
        "//th[contains(@class, 'ant-descriptions-item-label') and contains(., 'Total')]/following-sibling::td[contains(@class, 'ant-descriptions-item-content')]/span",
    ),
    # --- NUEVOS DATOS DE INTELIGENCIA ---
    "payment_method": (
        By.XPATH,
        "//span[contains(text(), 'Payment method:')]/ancestor::div[contains(@class, 'ant-space-item')][1]/following-sibling::div[1]//span",
    ),
    # Cancelación: (Se mantienen a la espera de confirmación visual si existen en la nueva vista)
    "cancellation_reason": (
        By.XPATH,
        "//span[contains(., 'Motivo de cancelación')]/following-sibling::span[contains(@class, 'info')]",
    ),
    "canceled_by": (
        By.XPATH,
        "//span[contains(., 'Cancelado por')]/following-sibling::span[contains(@class, 'info')]",
    ),
    # IDs para relaciones (Mantenemos por compatibilidad, aunque la vista nueva los ocultó)
    "store_link": (By.XPATH, "//a[contains(@href, 'store/view')]"),
    "customer_link": (By.XPATH, "//a[contains(@href, 'customer/view')]"),
    "driver_link": (By.XPATH, "//a[contains(@href, 'delivery-man/preview')]"),
    # --- CONFIGURACIÓN DE COMISIÓN (Business Plan) ---
    "commission_input": (By.ID, "comission"),
    "commission_text_pattern": r"(\d+(?:\.\d+)?)%\s*comisión",
    # --- NUEVOS SELECTORES DE TABLA DE PRODUCTOS (Ant Design) ---
    "product_table_rows": (By.CSS_SELECTOR, "tbody.ant-table-tbody tr.ant-table-row"),
    "product_col_tag": (By.CSS_SELECTOR, "td.ant-table-cell"),
    "product_name_tag": (By.CSS_SELECTOR, "span.ant-typography strong"),
    "product_qty_price_tag": (
        By.XPATH,
        ".//span[contains(@class, 'ant-typography')]/following-sibling::div",
    ),
    "product_barcode_tag": (By.CSS_SELECTOR, "svg text"),
    # --- FINANCIEROS Y PAGOS FALTANTES ---
    "financial_row_template": "//th[contains(@class, 'ant-descriptions-item-label') and contains(., '{label}')]/following-sibling::td//span",
    "payment_method_universal": (
        By.XPATH,
        "//span[contains(text(), 'Payment method') or contains(text(), 'Método de pago')]/parent::div/following-sibling::div//span",
    ),
    # --- FALLBACK DE MAPAS (Para evitar KeyError en el worker) ---
    "latitude_input": (By.XPATH, "//input[@id='latitude_inexistente']"),
    "longitude_input": (By.XPATH, "//input[@id='longitude_inexistente']"),
}

CUSTOMER_LIST_SELECTORS = {
    # --- TABLA Y PAGINACIÓN ---
    "table_body": (By.ID, "set-rows"),
    "table_rows": (By.CSS_SELECTOR, "tbody#set-rows tr"),
    "next_page_btn": (By.CSS_SELECTOR, "a.page-link[rel='next']"),
    # --- COLUMNAS (Relativas a la fila <tr>) ---
    "id_cell": (
        By.XPATH,
        ".//td[1]",
    ),  # Mantenemos el índice 1 porque es el ID crudo sin clases
    # Nombre: Buscamos el primer enlace que tenga la ruta /customer/view/ dentro de la columna 2
    "name_link": (By.XPATH, ".//td[2]//a[contains(@href, 'customer/view')]"),
    # Teléfono: Buscamos el enlace 'tel:' dentro de la fila
    "phone_link": (By.XPATH, ".//a[starts-with(@href, 'tel:')]"),
    # Fecha: Está en la penúltima columna visible, pero la penúltima es "Toggle status".
    # Por el HTML, la fecha está en la columna justo antes del toggle.
    # Usaremos el índice 7 por ahora, ya que no tiene clases distintivas (solo label badge).
    "joined_date_cell": (By.XPATH, ".//td[7]"),
}
