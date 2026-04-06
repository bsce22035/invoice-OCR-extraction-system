from flask import Flask, render_template, request, send_file
import easyocr
import cv2
import os
import re
import csv
import numpy as np
from difflib import get_close_matches
from pdf2image import convert_from_bytes

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static'
TEXT_CSV = os.path.join(app.config['UPLOAD_FOLDER'], 'ocr_text.csv')
TABLE_CSV = os.path.join(app.config['UPLOAD_FOLDER'], 'invoice_table.csv')

reader = easyocr.Reader(['en'])

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
        x1, y1 = lines[i]['x'], lines[i]['y']
        found = False

        for j in range(i + 1, min(i + 4, len(lines))):
            x2, y2 = lines[j]['x'], lines[j]['y']
            if 0 < (y2 - y1) < 80 and abs(x2 - x1) < 250:
                val = lines[j]['text']
                if 2 <= len(val) <= 60:
                    if re.search(r'(name|invoice|gst|ref|ntn|date|number|amount|total|grand|no\.?|#)$', key.lower()):
                        key_values[key] = val
                        found = True
                        break

        if not found and ':' in key:
            parts = re.split(r':{1,2}', key, maxsplit=1)
            key_clean = parts[0].strip()
            value = parts[1].strip() if len(parts) > 1 else ''

            if not value and (i + 1) < len(lines):
                next_line_text = lines[i + 1]['text'].strip()
                if len(next_line_text) > 2:
                    value = next_line_text

            if key_clean and value and key_clean not in key_values:
                key_values[key_clean] = value

        i += 1

    for i in range(len(lines) - 1):
        current = lines[i]
        next_line = lines[i + 1]
        if abs(current['y_raw'] - next_line['y_raw']) < 25 and next_line['x'] > current['x']:
            key_text = current['text'].strip()
            val_text = next_line['text'].strip()
            if re.search(r'(amount|total|grand|pst|gst|ntn)', key_text.lower()) and re.search(r'[\d,]+', val_text):
                if key_text not in key_values:
                    key_values[key_text] = val_text

    return key_values

def extract_table_rows(results):
    lines = [text.strip() for (_, text, _) in results]
    table_data = []
    header_found = False
    collecting = False

    for line in lines:
        line_lower = line.lower()

        if not header_found and re.search(r'(services|description|item no|particulars|qty|rate|amount)', line_lower):
            header_found = True
            collecting = True
            continue

        if collecting:
            if re.search(r'(grand total|total|gst|tax|subtotal|net amount)', line_lower):
                break

            # Accept short rows (1-2 columns) too
            columns = re.split(r'\s{2,}|	', line)
            if columns and any(c.strip() for c in columns):
                table_data.append(columns)

    return table_data

@app.route('/', methods=['GET', 'POST'])
def index():
    extracted_text = []
    numeric_values = []
    output_image_path = None
    key_value_fields = {}
    user_query = ''
    table_rows = []
    raw_lines = []
    matched_results = []

    if request.method == 'POST':
        user_query = request.form.get('user_key', '').strip()
        queries = [q.strip().lower() for q in user_query.split(',') if q.strip()]

        file = request.files.get('image')
        if file:
            filename = file.filename.lower()

            if filename.endswith('.pdf'):
                images = convert_from_bytes(file.read(), poppler_path=r"E:\softwares\poppler\poppler-24.08.0\Library\bin")
                image = cv2.cvtColor(np.array(images[0]), cv2.COLOR_RGB2BGR)
            else:
                input_path = os.path.join(app.config['UPLOAD_FOLDER'], 'input.jpg')
                file.save(input_path)
                image = cv2.imread(input_path)

            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            results = reader.readtext(image_rgb)

            raw_lines = [text for (_, text, _) in results]
            key_value_fields = extract_key_value_pairs(results)
            table_rows = extract_table_rows(results)

            # 🐞 Debug print
            print("📊 Extracted Table Rows:")
            for row in table_rows:
                print(row)

            for (bbox, text, prob) in results:
                confidence = round(prob * 100, 1)
                extracted_text.append((text, f"{confidence}%"))
                numeric_values.extend(re.findall(r'\d+(?:\.\d+)?', text))

                (tl, tr, br, bl) = bbox
                tl = tuple(map(int, tl))
                br = tuple(map(int, br))
                cv2.rectangle(image, tl, br, (0, 255, 0), 2)
                cv2.putText(image, text, tl, cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)

            output_path = os.path.join(app.config['UPLOAD_FOLDER'], 'output.jpg')
            cv2.imwrite(output_path, image)
            output_image_path = 'output.jpg'

            with open(TEXT_CSV, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['Detected Text', 'Confidence (%)'])
                for (text, conf) in extracted_text:
                    writer.writerow([text, conf])

            with open(TABLE_CSV, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                for row in table_rows:
                    writer.writerow(row)

            for query in queries:
                query_clean = re.sub(r'[^a-z0-9 ]', '', query.lower())

                normalized_map = {
                    re.sub(r'[^a-z0-9 ]', '', k.lower()): (k, v)
                    for k, v in key_value_fields.items()
                }

                if query_clean in normalized_map:
                    orig_k, val = normalized_map[query_clean]
                    matched_results.append((query, orig_k, val))
                    continue

                matches = get_close_matches(query_clean, normalized_map.keys(), n=3, cutoff=0.6)
                found = False
                for match in matches:
                    orig_k, val = normalized_map[match]
                    if query_clean in ['client name'] and 'ntn' in match:
                        continue
                    if all(word in match for word in query_clean.split()):
                        matched_results.append((query, orig_k, val))
                        found = True
                        break

                if not found and matches:
                    orig_k, val = normalized_map[matches[0]]
                    matched_results.append((query, orig_k, val))
                    continue

                if query in ['ntn', 'client ntn']:
                    all_ntns = [(k, v) for k, v in key_value_fields.items() if 'ntn' in k.lower()]
                    if all_ntns:
                        for k, v in all_ntns:
                            matched_results.append((query, k, v))
                        continue

                if query != 'services':
                    for (text, _) in extracted_text:
                        if query in text.lower():
                            matched_results.append((query, text, ''))
                            break
                    else:
                        matched_results.append((query, '', ''))

            # ✅ Extract services only from table
            if 'services' in queries:
                service_lines = []
                service_started = False

                for row in table_rows:
                    joined = " ".join(row).strip().lower()

                    if re.search(r'(services|description|item no|particulars)', joined):
                        service_started = True
                        continue

                    if service_started:
                        if re.search(r'(total|amount|gst|tax|grand)', joined):
                            break

                        if joined and not re.fullmatch(r'[\d,. ]+', joined) and len(joined) > 5:
                            service_lines.append(" ".join(row).strip())

                if service_lines:
                    combined = " • ".join(service_lines)
                    matched_results.append(('services', 'Service Items', combined))
                else:
                    matched_results.append(('services', '', ''))

    return render_template('index.html',
                           output_image=output_image_path,
                           extracted_text=extracted_text,
                           numeric_values=numeric_values,
                           key_value_fields=key_value_fields,
                           user_query=user_query,
                           matched_results=matched_results,
                           table_rows=table_rows,
                           raw_lines=raw_lines)

@app.route('/download_text_csv')
def download_text_csv():
    if os.path.exists(TEXT_CSV):
        return send_file(TEXT_CSV, as_attachment=True)
    return "Text CSV not found", 404

@app.route('/download_table_csv')
def download_table_csv():
    if os.path.exists(TABLE_CSV):
        return send_file(TABLE_CSV, as_attachment=True)
    return "Table CSV not found", 404

if __name__ == '__main__':
    app.run(debug=True)
