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
    "search_input": (By.ID, "datatableSearch_"),
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
    # --- INFO BÁSICA Y STATUS (Actualizado a Ant Design / React) ---
    "status_badge": (
        By.XPATH,
        "//span[contains(text(), 'Status:')]/ancestor::div[contains(@class, 'ant-space-item')][1]/following-sibling::div//span[@class='ant-select-selection-item']",
    ),
    "order_placed_at": (
        By.XPATH,
        "//span[@aria-label='calendar']/ancestor::div[contains(@class, 'ant-space-horizontal')]//div[contains(@class, 'ant-space-item')][2]/span",
    ),
    "order_type_label": (
        By.XPATH,
        "//span[contains(text(), 'Order type:')]/ancestor::div[contains(@class, 'ant-space-item')][1]/following-sibling::div//span",
    ),
    # --- TELÉFONO CLIENTE ---
    "customer_phone_link": (
        By.XPATH,
        "//div[contains(@class, 'ant-card-head-title') and contains(text(), 'Customer info')]/ancestor::div[contains(@class, 'ant-card')]//a[starts-with(@href, 'tel:')]",
    ),
    # --- NOMBRES PRINCIPALES (Extraídos de los Cards de Ant Design) ---
    "store_name": (
        By.XPATH,
        "//span[contains(text(), 'Store:')]/ancestor::div[contains(@class, 'ant-space-item')][1]/following-sibling::div//span[contains(@class, 'ant-tag')]",
    ),
    "customer_name": (
        By.XPATH,
        "//div[contains(@class, 'ant-card-head-title') and contains(text(), 'Customer info')]/ancestor::div[contains(@class, 'ant-card')]//h5",
    ),
    "driver_name": (
        By.XPATH,
        "//div[contains(@class, 'ant-card-head-title') and contains(text(), 'Delivery man')]/ancestor::div[contains(@class, 'ant-card')]//h5",
    ),
    # Montos
    "delivery_fee": (
        By.XPATH,
        "//dt[contains(normalize-space(), 'Tarifa de entrega') or contains(normalize-space(), 'Delivery fee')]/following-sibling::dd",
    ),
    "total_amount": (
        By.XPATH,
        "//dt[normalize-space()='Total:']/following-sibling::dd",
    ),
    # --- NUEVOS DATOS DE INTELIGENCIA ---
    # Método de pago: Buscamos el h6 que contiene el texto y tomamos el último span
    "payment_method": (
        By.XPATH,
        "//h6[contains(., 'Método de pago') or contains(., 'Payment method')]/span[last()]",
    ),
    # Cancelación: Buscamos en la tarjeta lateral derecha (sidebar)
    "cancellation_reason": (
        By.XPATH,
        "//span[contains(., 'Motivo de cancelación')]/following-sibling::span[contains(@class, 'info')]",
    ),
    "canceled_by": (
        By.XPATH,
        "//span[contains(., 'Cancelado por')]/following-sibling::span[contains(@class, 'info')]",
    ),
    # IDs para relaciones
    "store_link": (By.XPATH, "//a[contains(@href, 'store/view')]"),
    "customer_link": (By.XPATH, "//a[contains(@href, 'customer/view')]"),
    "driver_link": (By.XPATH, "//a[contains(@href, 'delivery-man/preview')]"),
    # --- CONFIGURACIÓN DE COMISIÓN (Business Plan) ---
    "commission_input": (By.ID, "comission"),
    "commission_text_pattern": r"(\d+(?:\.\d+)?)%\s*comisión",
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
