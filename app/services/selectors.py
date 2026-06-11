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
    # --- TABLA PRINCIPAL ---
    "table_body": (By.ID, "set-rows"),
    # Selecciona solo las filas de pedidos, ignorando las filas agrupadoras ("Cart XXXX")
    "order_rows": (
        By.CSS_SELECTOR, 
        "tbody#set-rows tr[class*='status-']"
    ),
    "order_id_link": (By.CSS_SELECTOR, "td.table-column-pl-0 a"),
    "duration_cell": (By.CSS_SELECTOR, "td:nth-child(2)"),
    
    # --- BÚSQUEDA Y FILTROS ---
    "search_input": (By.ID, "filter-search"),
    
    # --- EXPORTACIÓN ---
    "export_dropdown_btn": (
        By.CSS_SELECTOR, 
        "a[data-hs-unfold-target='#usersExportDropdown']"
    ),
    # Optimizado: El botón tiene un ID directo en el HTML, es más seguro que el XPath anterior
    "csv_export_btn": (By.ID, "export-csv"),
    "excel_export_btn": (By.ID, "export-excel"), # Te lo añado por si acaso
    
    # --- PAGINACIÓN ---
    "next_page_btn": (By.CSS_SELECTOR, "a.page-link[rel='next']"),
}

ORDER_DETAIL_SELECTORS = {
    # --- CABECERA Y ESTADO ---
    "status_badge": (
        By.XPATH,
        "//span[contains(normalize-space(.), 'Status:')]/ancestor::div[contains(@class, 'ant-space-item')][1]/following-sibling::div[1]//span"
    ),
    "order_placed_at": (
        By.XPATH,
        "//span[contains(@aria-label, 'calendar')]/ancestor::div[contains(@class, 'ant-space-item')][1]/following-sibling::div[1]/span"
    ),
    "order_type_label": (
        By.XPATH,
        "//span[contains(normalize-space(.), 'Order type:')]/ancestor::div[contains(@class, 'ant-space-item')][1]/following-sibling::div[1]//span"
    ),
    "payment_method": (
        By.XPATH,
        "//span[contains(normalize-space(.), 'Payment method:')]/ancestor::div[contains(@class, 'ant-space-item')][1]/following-sibling::div[1]//span"
    ),

    # --- TARJETAS DE INFORMACIÓN ---
    "customer_name": (
        By.XPATH, 
        "//div[@class='ant-card-head-title' and text()='Customer info']/../../..//h5"
    ),
    "driver_name": (
        By.XPATH, 
        "//div[@class='ant-card-head-title' and text()='Delivery man']/../../..//h5"
    ),
    "store_name": (
        By.XPATH, 
        "//div[@class='ant-card-head-title' and text()='Store info']/../../..//h5"
    ),
    
    # --- TELÉFONO DEL CLIENTE ---
    "customer_phone_link": (
        By.XPATH,
        "//div[@class='ant-card-head-title' and text()='Customer info']/../../..//a[starts-with(@href, 'tel:')]"
    ),

    # --- MONTOS ---
    "delivery_fee": (
        By.XPATH,
        "//th[contains(@class, 'ant-descriptions-item-label') and (contains(normalize-space(.), 'Delivery charge') or contains(normalize-space(.), 'Tarifa de entrega'))]/following-sibling::td//span"
    ),
    "total_amount": (
        By.XPATH,
        "//th[contains(@class, 'ant-descriptions-item-label') and contains(normalize-space(.), 'Total')]/following-sibling::td//span"
    ),
    "commission_text": (
        By.XPATH,
        "//th[contains(@class, 'ant-descriptions-item-label') and (contains(normalize-space(.), 'Commission') or contains(normalize-space(.), 'Comisión'))]/following-sibling::td//span"
    ),

    # --- TABLA DE PRODUCTOS ---
    "product_table_rows": (By.CSS_SELECTOR, "tbody.ant-table-tbody tr.ant-table-row"),
    "product_col_tag": (By.CSS_SELECTOR, "td.ant-table-cell"),
    "product_name_tag": (By.CSS_SELECTOR, "span.ant-typography strong"),
    "product_qty_price_tag": (
        By.XPATH,
        ".//span[contains(@class, 'ant-typography')]/following-sibling::div"
    ),
    "product_barcode_tag": (By.CSS_SELECTOR, "svg text"),

    # --- FALLBACK DE MAPAS ---
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
