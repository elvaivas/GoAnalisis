from selenium.webdriver.common.by import By

LOGIN_SELECTORS = {
    "email_input": (By.NAME, "email"),
    "password_input": (By.NAME, "password"),
    "login_button": (By.CSS_SELECTOR, "button[type='submit']"),
    "dashboard_indicator": (By.CSS_SELECTOR, "a[href='https://ecosistema.gopharma.com.ve/admin/order/list/all']")
}

ORDER_TABLE_SELECTORS = {
    "table_body": (By.ID, "set-rows"),
    "order_id_link": (By.CSS_SELECTOR, "td.table-column-pl-0 a"),
}

ORDER_DETAIL_SELECTORS = {
    "order_placed_at": (By.XPATH, "//i[@class='tio-date-range']/parent::span"),
    
    # Enlaces principales (IDs y Nombres)
    "store_name": (By.XPATH, "//a[contains(@href, 'store/view')]"),
    "customer_name": (By.XPATH, "//a[contains(@href, 'customer/view')]/div/span[contains(@class, 'font-semibold')]"),
    "driver_name": (By.XPATH, "//a[contains(@href, 'delivery-man/preview')]/div/span[1]"),
    
    # Montos
    "delivery_fee": (By.XPATH, "//dt[normalize-space()='Tarifa de entrega:']/following-sibling::dd"),
    "total_amount": (By.XPATH, "//dt[normalize-space()='Total:']/following-sibling::dd"),
    
    # --- NUEVOS DATOS DE INTELIGENCIA ---
    # Método de pago: Buscamos el h6 que contiene el texto y tomamos el último span
    "payment_method": (By.XPATH, "//h6[contains(., 'Método de pago')]/span[last()]"),
    
    # Cancelación: Buscamos en la tarjeta lateral derecha (sidebar)
    "cancellation_reason": (By.XPATH, "//span[contains(., 'Motivo de cancelación')]/following-sibling::span[contains(@class, 'info')]"),
    "canceled_by": (By.XPATH, "//span[contains(., 'Cancelado por')]/following-sibling::span[contains(@class, 'info')]"),
    
    # IDs para relaciones
    "store_link": (By.XPATH, "//a[contains(@href, 'store/view')]"),
    "customer_link": (By.XPATH, "//a[contains(@href, 'customer/view')]"),
    "driver_link": (By.XPATH, "//a[contains(@href, 'delivery-man/preview')]"),
}
