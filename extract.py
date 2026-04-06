import re

key_keywords = [
    'invoice', 'date', 'client', 'customer', 'name', 'ntn', 'ref', 'reference',
    'attn', 'attention', 'address', 'service', 'description', 'amount', 'total',
    'grand', 'gst', 'tax', 'pst', 'number', 'no', '#', 'bill', 'company',
    'registration', 'phone', 'mobile', 'month', 'account', 'bank'
]

alias_map = {
    "client ntn": "NTN",
    "ntn": "NTN",
    "sntn": "NTN",
    "client name": "Client Name",
    "attn": "Attention",
    "attention": "Attention",
    "number": "Invoice Number",
    "ref": "Reference",
    "reference": "Reference",
    "grand total": "Total Amount",
    "gst": "Sales Tax",
    "tax": "Sales Tax",
    "bank": "Bank",
    "account": "Account Number",
}

def extract_key_value_pairs(results):
    key_values = {}
    lines = []

    for (bbox, text, prob) in results:
        x1, y1 = int(bbox[0][0]), int(bbox[0][1])
        x2, y2 = int(bbox[2][0]), int(bbox[2][1])
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        lines.append({'text': text.strip(), 'x': cx, 'y': cy, 'y_raw': y1, 'bbox': bbox})

    lines = sorted(lines, key=lambda l: (l['y'], l['x']))
    i = 0

    while i < len(lines):
        key = lines[i]['text']
        key = re.sub(r':{2,}', ':', key)  # Convert :: to :

        x1, y1 = lines[i]['x'], lines[i]['y']
        found = False

        # Try vertical key-value pattern
        for j in range(i + 1, min(i + 4, len(lines))):
            x2, y2 = lines[j]['x'], lines[j]['y']
            if 0 < (y2 - y1) < 80 and abs(x2 - x1) < 250:
                val = lines[j]['text']
                if 2 <= len(val) <= 60:
                    if any(kw in key.lower() for kw in key_keywords):
                        key_values[key] = val
                        found = True
                        break

        if not found and ':' in key:
            parts = [p.strip() for p in re.split(r':', key) if p.strip()]

            if len(parts) == 2:
                k, v = parts
                v_norm = v.lower().strip().rstrip(':')

                is_value_bad = (
                    v_norm in key_keywords or
                    v_norm.endswith('name') or
                    len(v_norm) <= 2 or
                    re.fullmatch(r'[A-Za-z]+:?', v_norm)
                )

                # Fallback to next line if value is invalid
                if is_value_bad and (i + 1) < len(lines):
                    fallback_val = lines[i + 1]['text'].strip()
                    fallback_val_norm = fallback_val.lower().strip().rstrip(':')
                    if fallback_val_norm not in key_keywords and len(fallback_val_norm) > 3:
                        v = fallback_val
                    else:
                        i += 1
                        continue

                if k not in key_values:
                    key_values[k] = v

            elif len(parts) >= 4 and len(parts) % 2 == 0:
                for idx in range(0, len(parts), 2):
                    k, v = parts[idx], parts[idx + 1]
                    if k not in key_values:
                        key_values[k] = v

            elif len(parts) == 1 and (i + 1) < len(lines):
                k = parts[0]
                next_line_text = lines[i + 1]['text'].strip()
                if len(next_line_text) > 2:
                    key_values[k] = next_line_text

        i += 1

    # Try horizontal pairing
    for i in range(len(lines) - 1):
        current = lines[i]
        next_line = lines[i + 1]
        if abs(current['y_raw'] - next_line['y_raw']) < 25 and next_line['x'] > current['x']:
            key_text = current['text'].strip()
            val_text = next_line['text'].strip()
            if any(kw in key_text.lower() for kw in key_keywords) and re.search(r'[\d\w,\.]+', val_text):
                if key_text not in key_values:
                    key_values[key_text] = val_text

    # Normalize using aliases
    for original_key in list(key_values):
        norm_key = original_key.lower()
        for alias in alias_map:
            if alias in norm_key and alias_map[alias] not in key_values:
                key_values[alias_map[alias]] = key_values[original_key]

    return key_values

def extract_table_rows(results):
    text_lines = sorted(results, key=lambda r: r[0][0][1])
    rows = []
    row_buffer = []
    last_y = None

    for (bbox, text, prob) in text_lines:
        (_, y1), (_, _), (_, y2), (_, _) = bbox
        y_center = (y1 + y2) // 2

        if last_y is None:
            last_y = y_center

        if abs(y_center - last_y) < 25:
            row_buffer.append(text)
        else:
            if len(row_buffer) > 1:
                rows.append(row_buffer)
            row_buffer = [text]
        last_y = y_center

    if len(row_buffer) > 1:
        rows.append(row_buffer)

    if not rows:
        return []

    header = rows[0]
    data_rows = rows[1:]

    structured_table = []
    for row in data_rows:
        if len(row) < len(header):
            row += [""] * (len(header) - len(row))
        elif len(row) > len(header):
            row = row[:len(header)]
        structured_table.append(dict(zip(header, row)))

    return structured_table
