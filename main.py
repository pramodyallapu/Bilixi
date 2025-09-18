from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import os
import tempfile
import pandas as pd
import re
from datetime import datetime
import PyPDF2
import pdfplumber
import openpyxl
from openpyxl.styles import Font, Alignment
from typing import List, Dict, Tuple

app = FastAPI()

def extract_text_from_pdf(pdf_path):
    text_content = ""
    try:
        # Use PyPDF2 first (faster)
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                text_content += page.extract_text() + "\n"
        
        # If no text found, try pdfplumber (slower but better)
        if not text_content.strip():
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    text_content += page.extract_text() + "\n"
    except Exception as e:
        pass
    return text_content

def parse_insurance_claims(text_content):
    claims_data = []
    pattern_missed_lines = []  # Only track lines that matched complete pattern but couldn't be parsed
    lines = [line.strip() for line in text_content.split('\n') if line.strip()]
    current_account = ""
    current_patient = ""
    
    for line_num, line in enumerate(lines, 1):
        # Skip header/footer lines
        if any(word in line for word in ["Murphy", "Page:", "Overdue", "Unpaid", "Insurance", "Report Date", "System:", "Time:", "Run:"]):
            continue
            
        # Check if line starts with account and patient name pattern
        m = re.match(r"^([A-Z]{3,}\d*X?)\s+([A-Z][A-Za-z\.\'\s]+)", line)
        if m:
            current_account = m.group(1)
            current_patient = m.group(2).strip()
            rest = line[m.end():].strip()
            
            # Try to parse this line with the complete pattern
            parsed_successfully, extracted_data = parse_complete_pattern(rest, current_account, current_patient)
            
            if parsed_successfully:
                claims_data.append(extracted_data)
            else:
                # Only track if this line has the structure of a complete data row
                if has_complete_data_row_structure(rest):
                    pattern_missed_lines.append({
                        'line_number': line_num,
                        'account': current_account,
                        'patient': current_patient,
                        'content': line,
                        'reason': 'Complete pattern matched but parsing failed',
                        'extracted_data': extracted_data
                    })
        else:
            # For continuation lines with existing context, also try complete pattern parsing
            if current_account and current_patient:
                parsed_successfully, extracted_data = parse_complete_pattern(line, current_account, current_patient)
                
                if parsed_successfully:
                    claims_data.append(extracted_data)
                else:
                    # Only track if this continuation line has the structure of a complete data row
                    if has_complete_data_row_structure(line):
                        pattern_missed_lines.append({
                            'line_number': line_num,
                            'account': current_account,
                            'patient': current_patient,
                            'content': line,
                            'reason': 'Continuation line - complete pattern parsing failed',
                            'extracted_data': extracted_data
                        })
    
    return claims_data, pattern_missed_lines


def has_complete_data_row_structure(line_content):
    """Check if the line content has the structure of a complete data row (all 7 columns)"""
    tokens = line_content.split()
    
    # Should have multiple tokens to potentially contain all fields
    if len(tokens) < 5:
        return False
    
    # Look for dates (DOS field)
    has_date = any(re.match(r'\d{2}/\d{2}/\d{2}', token) for token in tokens)
    
    # Look for monetary values (Claim Amount and Over Due fields)
    has_monetary_values = len([token for token in tokens if re.match(r'^\$?[\d,]+\.?\d*$', token)]) >= 2
    
    # Look for insurance company (multiple words before indicators)
    has_insurance_company = False
    for i, token in enumerate(tokens):
        if token in ['Pri', 'Sec', 'Oth', 'E', 'W', 'P', 'F', 'H'] and i > 1:
            has_insurance_company = True
            break
    
    # Look for insurance ID (alphanumeric patterns at the end)
    has_insurance_id = any(re.match(r'^[A-Za-z0-9\-_]+$', token) for token in tokens[-2:])
    
    # Consider it a complete data row if it has date + monetary values + either insurance company or ID
    return has_date and has_monetary_values and (has_insurance_company or has_insurance_id)


def parse_complete_pattern(line_content, account, patient):
    """Parse line content using the complete pattern and return (success, extracted_data)"""
    tokens = line_content.split()
    if len(tokens) < 5:  # Need enough tokens for complete pattern
        return False, {}
        
    extracted_data = {
        'Account': account,
        'Patient Name': patient,
        'DOS': '',
        'Insurance Company': '',
        'Claim Amount': '',
        'Over Due': '',
        'Insurance ID': ''
    }
    
    # Find all dates in the entire line content (including concatenated dates)
    all_dates = re.findall(r'\d{2}/\d{2}/\d{2}', line_content)
    
    # Determine DOS based on number of dates found
    if len(all_dates) == 2:
        # If 2 dates: use first one
        extracted_data['DOS'] = all_dates[0]
    elif len(all_dates) == 3:
        # If 3 dates: use second one (as before)
        extracted_data['DOS'] = all_dates[1]
    elif len(all_dates) >= 4:
        # If 4+ dates: use third one (NEW LOGIC)
        extracted_data['DOS'] = all_dates[2]
    elif len(all_dates) == 1:
        # If 1 date: use it
        extracted_data['DOS'] = all_dates[0]
    
    if not extracted_data['DOS']:
        return False, extracted_data
        
    # Remove all dates from line content to get clean text for insurance parsing
    clean_content = line_content
    for date in all_dates:
        clean_content = clean_content.replace(date, ' ')
    
    # Clean up extra spaces and split into tokens
    clean_tokens = [token for token in clean_content.split() if token.strip()]
    
    # Find insurance company - collect tokens until we hit Pri/Sec/Oth
    i = 0
    insurance_parts = []
    while i < len(clean_tokens) and clean_tokens[i] not in ['Pri', 'Sec', 'Oth']:
        insurance_parts.append(clean_tokens[i])
        i += 1
    
    # Join the insurance parts
    insurance_name = ' '.join(insurance_parts)
    
    # Clean up the insurance name - remove account numbers and patient names
    insurance_tokens = insurance_name.split()
    cleaned_insurance_tokens = []
    
    # Common insurance company keywords to look for
    insurance_keywords = ['BLUE', 'CROSS', 'SHIELD', 'MEDICARE', 'MEDICAID', 'AETNA', 
                         'UNITED', 'HEALTH', 'CIGNA', 'HUMANA', 'ANTHEM', 'WELLCARE',
                         'CENTENE', 'MOLINA', 'KAISER', 'TRICARE', 'FEDERAL', 'COMMUNITY','SELECTIVE' ,'ADMINISTRATIV'
                         'MISSISSIPP', 'MISSISSIPPI', 'CARE', 'PLUS', 'PLAN', 'GROUP']
    
    # Find the start of the actual insurance company name
    start_index = 0
    for i, token in enumerate(insurance_tokens):
        if token in insurance_keywords or any(keyword in token for keyword in insurance_keywords):
            start_index = i
            break
    
    # Only keep tokens from the insurance keyword onward
    cleaned_insurance_tokens = insurance_tokens[start_index:]
    
    # If we have a cleaned insurance name, use it
    if cleaned_insurance_tokens:
        extracted_data['Insurance Company'] = ' '.join(cleaned_insurance_tokens)
    else:
        # Fallback to the original extraction
        extracted_data['Insurance Company'] = insurance_name
    
    # Continue with original tokens for the rest of parsing
    tokens = line_content.split()
    # Find position after insurance company in original tokens
    if insurance_parts:
        for idx, token in enumerate(tokens):
            if token == insurance_parts[-1]:
                i = idx + 1
                break
    else:
        i = 0
    
    # Skip Pri/Sec/Oth and E/W/P/F/H indicators
    if i < len(tokens) and tokens[i] in ['Pri', 'Sec', 'Oth']:
        i += 1
    if i < len(tokens) and tokens[i] in ['E', 'W', 'P', 'F', 'H']:
        i += 1
        
    # Get claim amount
    if i < len(tokens):
        try:
            extracted_data['Claim Amount'] = float(tokens[i].replace(',', ''))
            i += 1
        except:
            pass
            
    # Skip status words like "Hold"
    status_words = ['Hold', 'WtERA', 'Forwd', 'Paid', 'Denied', 'Rej', 'Reversed', 'Recoup', 'Offset']
    if i < len(tokens) and tokens[i] in status_words:
        i += 1
        
    # Get over due amount
    if i < len(tokens):
        try:
            extracted_data['Over Due'] = float(tokens[i].replace(',', ''))
            i += 1
        except:
            pass
                
    # Get insurance ID (remaining tokens)
    if i < len(tokens):
        insurance_id = ' '.join(tokens[i:])
        # Clean up insurance ID
        m_id = re.match(r'([A-Za-z0-9\-\_]+)', insurance_id)
        if m_id:
            extracted_data['Insurance ID'] = m_id.group(1)
        else:
            extracted_data['Insurance ID'] = insurance_id
    
    # Check if we have all essential data
    if (extracted_data['DOS'] and extracted_data['Insurance Company'] and 
        extracted_data['Claim Amount'] != ''):
        return True, extracted_data
    else:
        return False, extracted_data

def parse_insurance_claims_layout(pdf_path):
    """Parse insurance claims using layout/position-based approach with pdfplumber"""
    claims_data = []
    pattern_missed_lines = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                # Extract words with positions
                words = page.extract_words(use_text_flow=True, keep_blank_chars=False)
                if not words:
                    continue
                
                print(f"Page {page_num+1} has {len(words)} words")
                
                # Group words into lines by y-coordinate (more tolerant grouping)
                lines = {}
                for word in words:
                    y_key = round(word['top'], 2)  # More precise grouping
                    if y_key not in lines:
                        lines[y_key] = []
                    lines[y_key].append(word)
                
                # Sort lines by y-coordinate
                sorted_lines = sorted(lines.items())
                print(f"Found {len(sorted_lines)} lines")
                
                # Find header line (contains "Account" and "Patient")
                header_line = None
                header_y = None
                for y, line_words in sorted_lines:
                    line_text = ' '.join(w['text'] for w in line_words).lower()
                    if 'account' in line_text and ('patient' in line_text or 'patient name' in line_text):
                        header_line = line_words
                        header_y = y
                        print(f"Found header at y={y}: {line_text}")
                        break
                
                if not header_line:
                    print("No header found, skipping page")
                    continue
                
                # Map header words to columns - improved to avoid overlaps
                header_texts = [w['text'].lower() for w in header_line]
                column_ranges = {}
                
                print(f"Header words: {header_texts}")
                
                # Use fixed column positions that work well with Murphy PDF layout
                # These are based on typical positions and avoid overlaps
                column_ranges = {
                    'Account': (0, 60),
                    'Patient Name': (60, 180),
                    'DOS': (180, 280),
                    'Insurance Company': (280, 450),
                    'Claim Amount': (450, 520),
                    'Over Due': (520, 580),
                    'Insurance ID': (580, 800)
                }
                
                for col_name, (min_x, max_x) in column_ranges.items():
                    print(f"Column {col_name}: x={min_x:.1f}-{max_x:.1f}")
                
                # Process data lines (skip header)
                current_account = ""
                current_patient = ""
                data_lines_processed = 0
                
                for y, line_words in sorted_lines:
                    # Skip header line
                    if y == header_y:
                        continue
                    
                    # Skip empty lines
                    if not line_words:
                        continue
                    
                    line_text = ' '.join(w['text'] for w in line_words)
                    data_lines_processed += 1
                    
                    # Check if this line starts a new record (has account-like pattern)
                    first_word = line_words[0]['text']
                    if re.match(r'^[A-Z]{3,}\d*X?$', first_word):
                        # New record
                        current_account = first_word
                        current_patient = ""
                        
                        # Try to extract patient name from subsequent words
                        if len(line_words) > 1:
                            patient_parts = []
                            for word in line_words[1:]:
                                text = word['text']
                                # Stop if we hit a date or other non-name token
                                if re.match(r'\d{2}/\d{2}/\d{2}', text) or text in ['Pri', 'Sec', 'Oth']:
                                    break
                                if text.replace('.', '').replace("'", '').replace('-', '').replace(' ', '').isalpha():
                                    patient_parts.append(text)
                                else:
                                    break
                            current_patient = ' '.join(patient_parts)
                    
                    # Extract data by column position
                    row_data = {
                        'Account': current_account,
                        'Patient Name': current_patient,
                        'DOS': '',
                        'Insurance Company': '',
                        'Claim Amount': '',
                        'Over Due': '',
                        'Insurance ID': ''
                    }
                    
                    # Assign words to columns based on x-position
                    for word in line_words:
                        word_center = (word['x0'] + word['x1']) / 2
                        word_text = word['text']
                        
                        # Find which column this word belongs to
                        for col_name, (min_x, max_x) in column_ranges.items():
                            if min_x <= word_center <= max_x:
                                # Determine which field this word belongs to
                                if col_name == 'DOS' and re.match(r'\d{2}/\d{2}/\d{2}', word_text):
                                    if not row_data['DOS']:
                                        row_data['DOS'] = word_text
                                elif col_name == 'Insurance Company':
                                    if not row_data['Insurance Company']:
                                        row_data['Insurance Company'] = word_text
                                    else:
                                        row_data['Insurance Company'] += ' ' + word_text
                                elif col_name == 'Claim Amount':
                                    try:
                                        amount = float(word_text.replace(',', '').replace('$', ''))
                                        row_data['Claim Amount'] = amount
                                    except:
                                        pass
                                elif col_name == 'Over Due':
                                    try:
                                        overdue = float(word_text.replace(',', '').replace('$', ''))
                                        row_data['Over Due'] = overdue
                                    except:
                                        pass
                                elif col_name == 'Insurance ID':
                                    if re.match(r'^[A-Za-z0-9\-_]+$', word_text):
                                        row_data['Insurance ID'] = word_text
                                break
                    
                    # Validate and add row
                    if (row_data['DOS'] and row_data['Insurance Company'] and 
                        row_data['Claim Amount'] != ''):
                        claims_data.append(row_data)
                        if len(claims_data) <= 5:  # Debug first few claims
                            print(f"  Claim: {row_data}")
                    elif (row_data['DOS'] or row_data['Insurance Company'] or 
                          row_data['Claim Amount'] != ''):
                        # Partial data - track as missed
                        pattern_missed_lines.append({
                            'line_number': len(pattern_missed_lines) + 1,
                            'account': current_account,
                            'patient': current_patient,
                            'content': line_text,
                            'reason': 'Layout parsing partial data',
                            'extracted_data': row_data
                        })
                
                print(f"  Processed {data_lines_processed} data lines")
    
    except Exception as e:
        print(f"Layout parsing error: {e}")
        import traceback
        traceback.print_exc()
    
    return claims_data, pattern_missed_lines

def parse_insurance_claims_with_fallback(text_content, pdf_path=None):
    """Parse insurance claims with automatic fallback to layout-based parsing"""
    # Try pattern-based parsing first
    claims_data, pattern_missed_lines = parse_insurance_claims(text_content)
    
    # If we have a high ratio of missed lines and we have the PDF path, try layout parsing
    if (len(pattern_missed_lines) > len(claims_data) * 0.1 and  # More than 10% missed
        pdf_path and os.path.exists(pdf_path)):
        
        print("High pattern-missed ratio detected, trying layout-based parsing...")
        layout_claims, layout_missed = parse_insurance_claims_layout(pdf_path)
        
        # Use layout results if they're better (more claims or fewer missed)
        if len(layout_claims) > len(claims_data) or len(layout_missed) < len(pattern_missed_lines):
            print(f"Using layout parsing: {len(layout_claims)} claims, {len(layout_missed)} missed")
            return layout_claims, layout_missed
        else:
            print(f"Keeping pattern parsing: {len(claims_data)} claims, {len(pattern_missed_lines)} missed")
    
    return claims_data, pattern_missed_lines

def create_xlsx_file(claims_data, pattern_missed_data, output_path):
    # Create main claims sheet
    columns = ['Account', 'Patient Name', 'DOS', 'Insurance Company', 'Claim Amount', 'Over Due', 'Insurance ID']
    df_claims = pd.DataFrame(claims_data, columns=columns)
    
    # Create pattern missed data sheet (only if there are missed lines)
    if pattern_missed_data:
        # Flatten the extracted data for the missed lines
        missed_records = []
        for missed_line in pattern_missed_data:
            record = {
                'line_number': missed_line['line_number'],
                'account': missed_line['account'],
                'patient': missed_line['patient'],
                'reason': missed_line['reason'],
                'content': missed_line['content']
            }
            # Add all extracted data fields
            for field in ['DOS', 'Insurance Company', 'Claim Amount', 'Over Due', 'Insurance ID']:
                record[field] = missed_line['extracted_data'].get(field, '')
            missed_records.append(record)
        
        missed_columns = ['line_number', 'account', 'patient', 'reason', 'content', 
                         'DOS', 'Insurance Company', 'Claim Amount', 'Over Due', 'Insurance ID']
        df_missed = pd.DataFrame(missed_records, columns=missed_columns)
    else:
        # Create empty dataframe with same structure
        missed_columns = ['line_number', 'account', 'patient', 'reason', 'content', 
                         'DOS', 'Insurance Company', 'Claim Amount', 'Over Due', 'Insurance ID']
        df_missed = pd.DataFrame(columns=missed_columns)
    
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        # Write claims data
        df_claims.to_excel(writer, sheet_name='Insurance Claims', index=False)
        
        # Write pattern missed data
        df_missed.to_excel(writer, sheet_name='Pattern Missed Data', index=False)
        
        # Format both sheets
        workbook = writer.book
        
        # Format Insurance Claims sheet
        worksheet_claims = writer.sheets['Insurance Claims']
        header_font = Font(bold=True)
        header_alignment = Alignment(horizontal='center')
        
        for col_num, column_title in enumerate(df_claims.columns, 1):
            cell = worksheet_claims.cell(row=1, column=col_num)
            cell.font = header_font
            cell.alignment = header_alignment
        
        for column in worksheet_claims.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            worksheet_claims.column_dimensions[column_letter].width = adjusted_width
        
        # Format Pattern Missed Data sheet
        worksheet_missed = writer.sheets['Pattern Missed Data']
        
        for col_num, column_title in enumerate(df_missed.columns, 1):
            cell = worksheet_missed.cell(row=1, column=col_num)
            cell.font = header_font
            cell.alignment = header_alignment
        
        for column in worksheet_missed.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            worksheet_missed.column_dimensions[column_letter].width = adjusted_width

@app.get("/", response_class=HTMLResponse)
async def read_root():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Insurance Claims PDF to Excel Converter</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <style>
            :root {
                --primary: #4361ee;
                --primary-dark: #3a56d4;
                --secondary: #7209b7;
                --success: #06d6a0;
                --warning: #ffd166;
                --error: #ef476f;
                --light: #f8f9fa;
                --dark: #212529;
                --gray: #6c757d;
                --border-radius: 12px;
                --box-shadow: 0 10px 25px rgba(0, 0, 0, 0.1);
                --transition: all 0.3s ease;
            }
            
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #f5f7fa 0%, #e4e9f2 100%);
                color: var(--dark);
                line-height: 1.6;
                min-height: 100vh;
                padding: 20px;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
            }
            
            .container {
                width: 100%;
                max-width: 900px;
                background: white;
                border-radius: var(--border-radius);
                box-shadow: var(--box-shadow);
                overflow: hidden;
                margin: 20px;
            }
            
            header {
                background: linear-gradient(to right, var(--primary), var(--secondary));
                color: white;
                padding: 30px;
                text-align: center;
            }
            
            header h1 {
                font-size: 2.2rem;
                margin-bottom: 10px;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 15px;
            }
            
            header p {
                font-size: 1.1rem;
                opacity: 0.9;
            }
            
            .content {
                padding: 30px;
            }
            
            .card {
                background: var(--light);
                border-radius: var(--border-radius);
                padding: 25px;
                margin-bottom: 25px;
                box-shadow: 0 4px 10px rgba(0, 0, 0, 0.05);
            }
            
            h2 {
                color: var(--primary);
                margin-bottom: 15px;
                display: flex;
                align-items: center;
                gap: 10px;
            }
            
            .upload-area {
                border: 2px dashed #ccc;
                border-radius: var(--border-radius);
                padding: 40px 20px;
                text-align: center;
                margin: 20px 0;
                transition: var(--transition);
                cursor: pointer;
                position: relative;
            }
            
            .upload-area:hover, .upload-area.dragover {
                border-color: var(--primary);
                background-color: rgba(67, 97, 238, 0.05);
            }
            
            .upload-area i {
                font-size: 3rem;
                color: var(--primary);
                margin-bottom: 15px;
            }
            
            .upload-area p {
                margin: 10px 0;
                color: var(--gray);
            }
            
            .upload-area .browse {
                color: var(--primary);
                font-weight: 600;
            }
            
            #pdfFile {
                display: none;
            }
            
            .file-info {
                display: none;
                margin-top: 15px;
                padding: 15px;
                background: white;
                border-radius: var(--border-radius);
                border-left: 4px solid var(--primary);
            }
            
            .file-info.active {
                display: flex;
                align-items: center;
                gap: 15px;
            }
            
            .file-info i {
                font-size: 2rem;
                color: var(--primary);
            }
            
            .file-details {
                flex-grow: 1;
            }
            
            .file-name {
                font-weight: 600;
                margin-bottom: 5px;
            }
            
            .file-size {
                color: var(--gray);
                font-size: 0.9rem;
            }
            
            .remove-btn {
                background: none;
                border: none;
                color: var(--gray);
                cursor: pointer;
                font-size: 1.2rem;
                transition: var(--transition);
            }
            
            .remove-btn:hover {
                color: #dc3545;
            }
            
            button {
                background: var(--primary);
                color: white;
                padding: 14px 28px;
                border: none;
                border-radius: 50px;
                cursor: pointer;
                font-size: 1.1rem;
                font-weight: 600;
                transition: var(--transition);
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: 10px;
                width: 100%;
                box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3);
            }
            
            button:hover {
                background: var(--primary-dark);
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(67, 97, 238, 0.4);
            }
            
            button:disabled {
                background: var(--gray);
                cursor: not-allowed;
                transform: none;
                box-shadow: none;
            }
            
            .result {
                margin-top: 25px;
                padding: 20px;
                border-radius: var(--border-radius);
                background: white;
                display: none;
                border-left: 4px solid var(--success);
                box-shadow: 0 4px 10px rgba(0, 0, 0, 0.05);
            }
            
            .result.success {
                display: block;
                border-left-color: var(--success);
            }
            
            .result.error {
                display: block;
                border-left-color: var(--error);
            }
            
            .result.warning {
                display: block;
                border-left-color: var(--warning);
            }
            
            .progress {
                margin-top: 20px;
                display: none;
            }
            
            .progress-bar {
                height: 8px;
                background: #e9ecef;
                border-radius: 4px;
                overflow: hidden;
            }
            
            .progress-bar-fill {
                height: 100%;
                background: linear-gradient(to right, var(--primary), var(--secondary));
                width: 0%;
                transition: width 0.4s ease;
            }
            
            .progress-text {
                text-align: center;
                margin-top: 10px;
                color: var(--gray);
                font-size: 0.9rem;
            }
            
            .download-btn {
                margin-top: 15px;
                background: var(--success);
                display: none;
            }
            
            .download-btn:hover {
                background: #05b387;
            }
            
            .features {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px;
                margin-top: 30px;
            }
            
            .feature {
                display: flex;
                align-items: flex-start;
                gap: 15px;
            }
            
            .feature i {
                background: var(--primary);
                color: white;
                width: 40px;
                height: 40px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
            }
            
            footer {
                text-align: center;
                margin-top: 30px;
                color: var(--gray);
                font-size: 0.9rem;
            }
            
            @media (max-width: 768px) {
                header {
                    padding: 20px;
                }
                
                header h1 {
                    font-size: 1.8rem;
                }
                
                .content {
                    padding: 20px;
                }
                
                .features {
                    grid-template-columns: 1fr;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <h1><i class="fas fa-file-excel"></i> PDF to Excel Converter</h1>
                <p>Transform your Insurance Claims PDF documents into organized Excel spreadsheets</p>
            </header>
            
            <div class="content">
                <div class="card">
                    <h2><i class="fas fa-upload"></i> Upload PDF File</h2>
                    <p>Select your insurance claims PDF document or drag and drop it below</p>
                    
                    <div class="upload-area" id="dropArea">
                        <i class="fas fa-cloud-upload-alt"></i>
                        <p>Drag & drop your PDF file here</p>
                        <p>or</p>
                        <p class="browse">Browse files</p>
                        <input type="file" id="pdfFile" name="file" accept=".pdf">
                    </div>
                    
                    <div class="file-info" id="fileInfo">
                        <i class="fas fa-file-pdf"></i>
                        <div class="file-details">
                            <div class="file-name" id="fileName">document.pdf</div>
                            <div class="file-size" id="fileSize">0 KB</div>
                        </div>
                        <button class="remove-btn" id="removeFile">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                    
                    <button id="convertBtn" disabled>
                        <i class="fas fa-sync-alt"></i> Convert to Excel
                    </button>
                    
                    <div class="progress" id="progressContainer">
                        <div class="progress-bar">
                            <div class="progress-bar-fill" id="progressBar"></div>
                        </div>
                        <div class="progress-text" id="progressText">Processing... 0%</div>
                    </div>
                    
                    <div class="result" id="result"></div>
                </div>
                
                <h2><i class="fas fa-star"></i> Why Choose Our Converter</h2>
                <div class="features">
                    <div class="feature">
                        <i class="fas fa-shield-alt"></i>
                        <div>
                            <h3>Secure Processing</h3>
                            <p>Your files are processed securely and never stored on our servers</p>
                        </div>
                    </div>
                    <div class="feature">
                        <i class="fas fa-bolt"></i>
                        <div>
                            <h3>Fast Conversion</h3>
                            <p>Advanced algorithms ensure quick conversion even for large files</p>
                        </div>
                    </div>
                    <div class="feature">
                        <i class="fas fa-chart-line"></i>
                        <div>
                            <h3>Accurate Data</h3>
                            <p>Maintain data integrity with precise table recognition technology</p>
                        </div>
                    </div>
                </div>
            </div>
            
            <footer>
                <p>© 2023 PDF to Excel Converter. All rights reserved.</p>
            </footer>
        </div>

        <script>
            document.addEventListener('DOMContentLoaded', function() {
                const dropArea = document.getElementById('dropArea');
                const fileInput = document.getElementById('pdfFile');
                const fileInfo = document.getElementById('fileInfo');
                const fileName = document.getElementById('fileName');
                const fileSize = document.getElementById('fileSize');
                const removeFile = document.getElementById('removeFile');
                const convertBtn = document.getElementById('convertBtn');
                const result = document.getElementById('result');
                const progressContainer = document.getElementById('progressContainer');
                const progressBar = document.getElementById('progressBar');
                const progressText = document.getElementById('progressText');
                
                let selectedFile = null;
                
                // Click on drop area to trigger file input
                dropArea.addEventListener('click', () => {
                    fileInput.click();
                });
                
                // Prevent default drag behaviors
                ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
                    dropArea.addEventListener(eventName, preventDefaults, false);
                    document.body.addEventListener(eventName, preventDefaults, false);
                });
                
                // Highlight drop area when file is dragged over it
                ['dragenter', 'dragover'].forEach(eventName => {
                    dropArea.addEventListener(eventName, highlight, false);
                });
                
                ['dragleave', 'drop'].forEach(eventName => {
                    dropArea.addEventListener(eventName, unhighlight, false);
                });
                
                // Handle dropped files
                dropArea.addEventListener('drop', handleDrop, false);
                
                // Handle file selection via input
                fileInput.addEventListener('change', handleFileSelect, false);
                
                // Remove selected file
                removeFile.addEventListener('click', function(e) {
                    e.stopPropagation();
                    resetFile();
                });
                
                // Convert button click
                convertBtn.addEventListener('click', convertFile);
                
                function preventDefaults(e) {
                    e.preventDefault();
                    e.stopPropagation();
                }
                
                function highlight() {
                    dropArea.classList.add('dragover');
                }
                
                function unhighlight() {
                    dropArea.classList.remove('dragover');
                }
                
                function handleDrop(e) {
                    const dt = e.dataTransfer;
                    const files = dt.files;
                    
                    if (files.length > 0) {
                        handleFiles(files[0]);
                    }
                }
                
                function handleFileSelect() {
                    if (fileInput.files.length > 0) {
                        handleFiles(fileInput.files[0]);
                    }
                }
                
                function handleFiles(file) {
                    if (file.type !== 'application/pdf') {
                        showResult('Please select a PDF file.', 'error');
                        return;
                    }
                    
                    selectedFile = file;
                    fileName.textContent = file.name;
                    fileSize.textContent = formatFileSize(file.size);
                    fileInfo.classList.add('active');
                    convertBtn.disabled = false;
                    
                    // Hide any previous results
                    result.style.display = 'none';
                }
                
                function resetFile() {
                    selectedFile = null;
                    fileInput.value = '';
                    fileInfo.classList.remove('active');
                    convertBtn.disabled = true;
                    progressContainer.style.display = 'none';
                    result.style.display = 'none';
                }
                
                function formatFileSize(bytes) {
                    if (bytes === 0) return '0 Bytes';
                    
                    const k = 1024;
                    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
                    const i = Math.floor(Math.log(bytes) / Math.log(k));
                    
                    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
                }
                
                function simulateProgress() {
                    let progress = 0;
                    progressContainer.style.display = 'block';
                    
                    const interval = setInterval(() => {
                        progress += Math.random() * 10;
                        if (progress >= 100) {
                            progress = 100;
                            clearInterval(interval);
                            progressBar.style.width = '100%';
                            progressText.textContent = 'Processing... 100%';
                        } else {
                            progressBar.style.width = progress + '%';
                            progressText.textContent = `Processing... ${Math.round(progress)}%`;
                        }
                    }, 300);
                }
                
                function convertFile() {
                    if (!selectedFile) {
                        showResult('Please select a PDF file first.', 'error');
                        return;
                    }
                    
                    // Create FormData object to send file
                    const formData = new FormData();
                    formData.append('file', selectedFile);
                    
                    // Show progress
                    simulateProgress();
                    
                    // Send the file to the server
                    fetch('/upload/', {
                        method: 'POST',
                        body: formData
                    })
                    .then(response => {
                        // Store response for use in the next then block
                        const responseClone = response.clone();
                        
                        if (response.ok) {
                            return response.blob().then(blob => {
                                return { blob, response: responseClone };
                            });
                        }
                        return response.text().then(text => {
                            throw new Error(text || 'Conversion failed');
                        });
                    })
                    .then(({ blob, response }) => {
                        // Create download URL
                        const url = window.URL.createObjectURL(blob);
                        
                        // Get filename from response headers
                        const contentDisposition = response.headers.get('content-disposition');
                        let filename = 'insurance_claims.xlsx';
                        
                        if (contentDisposition) {
                            // Try multiple patterns for filename extraction
                            let filenameMatch = contentDisposition.match(/filename="([^"]+)"/);
                            if (!filenameMatch) {
                                filenameMatch = contentDisposition.match(/filename=([^;]+)/);
                            }
                            if (filenameMatch) {
                                filename = filenameMatch[1].trim();
                            }
                        }
                        
                        // Create a temporary anchor element for download
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = filename;
                        document.body.appendChild(a);
                        a.click();
                        document.body.removeChild(a);
                        
                        // Clean up URL
                        window.URL.revokeObjectURL(url);
                        
                        // Hide progress
                        progressContainer.style.display = 'none';
                        
                        // Show success message
                        result.innerHTML = `
                            <h3><i class="fas fa-check-circle"></i> Conversion Successful!</h3>
                            <p>Your file "${selectedFile.name}" has been converted to Excel format.</p>
                            <p>Downloaded as: <strong>${filename}</strong></p>
                        `;
                        result.classList.add('success');
                        result.style.display = 'block';
                    })
                    .catch(error => {
                        // Hide progress
                        progressContainer.style.display = 'none';
                        
                        // Show error
                        showResult('Error: ' + error.message, 'error');
                    });
                }
                
                function showResult(message, type) {
                    result.innerHTML = `<p>${message}</p>`;
                    result.className = 'result';
                    result.classList.add(type);
                    result.style.display = 'block';
                    
                    // Scroll to result
                    result.scrollIntoView({ behavior: 'smooth' });
                }
            });
        </script>
    </body>
    </html>
    """

@app.post("/upload/")
async def upload_file(file: UploadFile = File(...)):
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    temp_pdf_path = None
    temp_xlsx_path = None

    try:
        # Save uploaded PDF
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_pdf:
            content = await file.read()
            temp_pdf.write(content)
            temp_pdf_path = temp_pdf.name

        # Extract text
        text_content = extract_text_from_pdf(temp_pdf_path)
        if not text_content.strip():
            raise HTTPException(status_code=400, detail="No text extracted from PDF")

        # Parse claims and get pattern-missed lines
        claims_data, pattern_missed_data = parse_insurance_claims_with_fallback(text_content, temp_pdf_path)
        
        if not claims_data and not pattern_missed_data:
            # Save debug file
            with open('debug_text.txt', 'w', encoding='utf-8') as f:
                f.write(text_content)
            raise HTTPException(status_code=400, detail="No data found in PDF")

        # Generate output filename based on input filename
        input_name = file.filename
        print(f"Input filename: '{input_name}'")
        if input_name.startswith('Biloxi'):
            import re
            date_match = re.search(r'(\d{8})', input_name)
            if date_match:
                date_str = date_match.group(1)
                try:
                    from datetime import datetime, timedelta
                    date_obj = datetime.strptime(date_str, '%m%d%Y')
                    next_date = date_obj + timedelta(days=1)
                    new_date_str = next_date.strftime('%m%d%Y')
                    output_filename = f"Bilxy {new_date_str}.xlsx"
                    print(f"Generated filename: '{output_filename}'")
                except Exception as e:
                    print(f"Date parsing error: {e}")
                    output_filename = "Bilxy_output.xlsx"
            else:
                print("No date found in filename")
                output_filename = "Bilxy_output.xlsx"
        else:
            base_name = input_name.rsplit('.', 1)[0]
            output_filename = f"{base_name}_processed.xlsx"

        print(f"Final output filename: '{output_filename}'")

        # Create Excel file with both sheets
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as temp_xlsx:
            temp_xlsx_path = temp_xlsx.name

        create_xlsx_file(claims_data, pattern_missed_data, temp_xlsx_path)

        # Return the Excel file
        from fastapi.responses import FileResponse
        response = FileResponse(
            temp_xlsx_path,
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            filename=output_filename
        )
        response.headers["Content-Disposition"] = f'attachment; filename="{output_filename}"'
        return response
    
    except Exception as e:
        # Clean up on error
        if temp_pdf_path and os.path.exists(temp_pdf_path):
            os.unlink(temp_pdf_path)
        if temp_xlsx_path and os.path.exists(temp_xlsx_path):
            os.unlink(temp_xlsx_path)
        raise HTTPException(status_code=500, detail=str(e))
    
    finally:
        # Only clean up PDF file
        if temp_pdf_path and os.path.exists(temp_pdf_path):
            os.unlink(temp_pdf_path)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)