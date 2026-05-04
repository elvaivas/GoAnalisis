file_path = "app/services/kpi_service.py"
with open(file_path, "r") as f:
    lines = f.readlines()

new_lines = []
skip = False
for i, line in enumerate(lines):
    # Detectamos el bloque donde se calcula el tiempo con los datos corruptos
    if "if (" in line and i+2 < len(lines) and "duration_val == 0" in lines[i+1]:
        skip = True
        indent = line[:len(line) - len(line.lstrip())]
        new_lines.append(indent + "# 🚨 SRE FIX: Ignoramos el Scraper y calculamos con precisión matemática usando los Logs\n")
        new_lines.append(indent + "done_log = next((l for l in o.status_logs if l.status == 'delivered'), None)\n")
        new_lines.append(indent + "start_log = next((l for l in o.status_logs if l.status == 'pending'), None)\n")
        new_lines.append(indent + "if done_log and start_log:\n")
        new_lines.append(indent + "    duration_val = int((done_log.timestamp - start_log.timestamp).total_seconds() / 60)\n")
        new_lines.append(indent + "elif done_log and o.created_at:\n")
        new_lines.append(indent + "    duration_val = int((done_log.timestamp - o.created_at).total_seconds() / 60)\n")
        
    # Fin del reemplazo
    if skip and "if 0 < duration_val < 600:" in line:
        skip = False
        
    if not skip:
        new_lines.append(line)

with open(file_path, "w") as f:
    f.writelines(new_lines)
print("✅ Código parcheado con éxito. Los tiempos ahora son inmortales.")
