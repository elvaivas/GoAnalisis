def scrape_store_list(self) -> list:
    """
    Escanea la lista principal de tiendas para extraer Empresa, Sucursal e ID real.
    """
    if not self.driver:
        self.setup_driver()
        self.login()

    url = f"{settings.LEGACY_BASE_URL}/admin/store/list"
    stores_data = []

    try:
        self.driver.get(url)
        WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.ID, "columnSearchDatatable"))
        )

        rows = self.driver.find_elements(
            By.XPATH, "//table[@id='columnSearchDatatable']/tbody/tr"
        )
        for row in rows:
            try:
                # 1. Empresa (Quitamos los puntos suspensivos si los trae)
                company_el = row.find_element(
                    By.XPATH, ".//span[contains(@class, 'badge-soft-info')]"
                )
                company_name = company_el.text.replace("...", "").strip()

                # 2. Sucursal (Sacamos el nombre COMPLETO desde el atributo 'title')
                title_el = row.find_element(
                    By.XPATH, ".//div[contains(@class, 'text--title')]"
                )
                store_name = title_el.get_attribute("title").strip()

                # 3. ID Real
                id_el = row.find_element(
                    By.XPATH,
                    ".//div[contains(@class, 'font-light') and contains(text(), 'ID:')]",
                )
                store_id = id_el.text.replace("ID:", "").strip()

                if store_id.isdigit():
                    stores_data.append(
                        {
                            "id": store_id,
                            "company_name": company_name,
                            "name": store_name,
                        }
                    )
            except Exception as e:
                continue

    except Exception as e:
        logger.error(f"Error scraping store list: {e}")

    return stores_data
