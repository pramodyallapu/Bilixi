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

        # Insert a space between account number and patient name if it's missing
        line = re.sub(r'(?<=[0-9X])(?=[A-Z])', ' ', line, 1)
            
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
    has_monetary_values = len([token for token in tokens if re.match(r'^\$?["\d,"]+\.?\d*$', token)]) >= 2
    
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
        m_id = re.match(r'([A-Za-z0-9\-_]+)', insurance_id)
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
