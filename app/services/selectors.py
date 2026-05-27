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
    # --- INFO BÁSICA Y STATUS (Sacados de la vista de detalles /admin/order/details/...) ---
    "status_badge": (
        By.XPATH,
        "//h6[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'status')]/span[contains(@class, 'badge')]",
    ),
    # --- INTERNOS DE LA TABLA DE PRODUCTOS (Relativos a la fila <tr>) ---
    "product_col_tag": (By.TAG_NAME, "td"),
    "product_name_tag": (By.TAG_NAME, "strong"),
    "product_qty_price_tag": (By.TAG_NAME, "h6"),
    # --- PLANTILLAS DINÁMICAS ---
    # Nota: Esto es un string, no una tupla (By.XPATH, "..."), porque necesita un .format(label=...)
    "financial_row_template": "//dl[contains(@class, 'row')]//dt[contains(., '{label}')]/following-sibling::dd[1]",
    "order_placed_at": (
        By.XPATH,
        "//i[contains(@class, 'tio-date-range')]/parent::span",
    ),
    "order_type_label": (
        By.XPATH,
        "//h6[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'order type') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'tipo de')]/label",
    ),
    # --- TELÉFONO CLIENTE (Card lateral derecha en detalles) ---
    "customer_phone_link": (
        By.XPATH,
        "//a[contains(@href, 'customer/view')]/ancestor::div[contains(@class, 'card')]//a[starts-with(@href, 'tel:')]",
    ),
    # --- MAPAS Y COORDENADAS (Inputs ocultos o visibles del modal de envío) ---
    "latitude_input": (By.ID, "latitude"),
    "longitude_input": (By.ID, "longitude"),
    # --- TABLA DE PRODUCTOS (Tabla central de la orden) ---
    "product_table_rows": (By.CSS_SELECTOR, "table.table tbody tr"),
    # --- PAGOS Y CANCELACIÓN ---
    "payment_method_universal": (
        By.XPATH,
        "//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'método de pago') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'payment method')]/parent::*",
    ),
    "cancellation_reason_labels": (
        By.XPATH,
        "//*[contains(text(), 'Motivo de cancelación') or contains(text(), 'Razón')]",
    ),
    # Enlaces principales (IDs y Nombres)
    "store_name": (By.XPATH, "//a[contains(@href, 'store/view')]"),
    "customer_name": (
        By.XPATH,
        "//a[contains(@href, 'customer/view')]/div/span[contains(@class, 'font-semibold')]",
    ),
    "driver_name": (
        By.XPATH,
        "//a[contains(@href, 'delivery-man/preview')]/div/span[1]",
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
