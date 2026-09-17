#!/bin/bash
# generate-manifest.sh - Автоматически сканирует /opt/father-80/web/images/
# и создает /opt/father-80/web/data/images.json
# Поддерживает только *.webp файлы
# Использует natural sorting по имени

IMAGES_DIR="/opt/father-80/web/images"
DATA_DIR="/opt/father-80/web/data"
MANIFEST_FILE="${DATA_DIR}/images.json"

# Создаем данные директорий, если их нет
mkdir -p "${DATA_DIR}"

# Собираем список *.webp файлов
shopt -s nullglob
files=("${IMAGES_DIR}"/*.webp)
shopt -u nullglob

# Натуральная сортировка через sort -V (version sort)
# sort -V корректно обрабатывает числа в именах файлов:
# slide-2.webp идет перед slide-10.webp
sorted_files=()

for f in "${files[@]}"; do
    basename="$(basename "$f")"
    sorted_files+=("$basename")
done

# sort -V (version sort) для натуральной сортировки
# -V флаг сортирует по версии (handles embedded numbers naturally)
if [ ${#sorted_files[@]} -gt 0 ]; then
    sorted_files=($(printf '%s\n' "${sorted_files[@]}" | sort -V))
fi

# Формируем JSON массив
json_array="["
first=true

for filename in "${sorted_files[@]}"; do
    # Экранируем специальные символы для JSON
    json_filename=$(printf '%s' "$filename" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\r/\\r/g; s/\n/\\n/g')

    if [ "$first" = true ]; then
        first=false
    else
        json_array="${json_array},"
    fi

    json_array="${json_array}{\"path\": \"${json_filename}\"}"
done

json_array="${json_array}]"

# Если файлов нет, создаем пустой массив
if [ "$first" = true ]; then
    json_array="[]"
fi

# Считаем количество
count=${#sorted_files[@]}

# Записываем manifest
cat > "${MANIFEST_FILE}" << EOF
{
  "count": ${count},
  "images": ${json_array}
}
EOF

echo "Manifest generated: ${MANIFEST_FILE} with ${count} images"
