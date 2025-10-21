import pandas as pd
import re
import PyPDF2
import pdfplumber
import openpyxl
from openpyxl.styles import Font, Alignment

def extract_text_from_pdf(pdf_path):
    text_content = ""
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                text_content += page.extract_text() + "\n"
        
        if not text_content.strip():
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    text_content += page.extract_text() + "\n"
    except Exception as e:
        pass
    return text_content

def parse_unpaid_charges(text_content):
    charges_data = []
    lines = [line.strip() for line in text_content.split('\n') if line.strip()]
    
    current_payor_primary = ""
    current_payor_secondary = ""
    

    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Skip header/footer lines
        if any(word in line.upper() for word in ["UNPAID CHARGES", "FILTER:", "PRINTED ON:", "PAGE #:", "TOTAL UNITS:", "TOTAL CHARGES:"]):
            i += 1
            continue
        
        # Skip column headers
        if "Date" in line and ("Patient" in line or "Code" in line):
            i += 1
            continue
            
        # Extract Payor information
        if "Payor:" in line:

            # Reset payor values for new payor line
            current_payor_primary = ""
            current_payor_secondary = ""
            
            # Extract Primary payor (exclude Office)
            primary_match = re.search(r'Primary:([^\s]+(?:\s+[^\s]+)*?)(?:\s+Secondary:|\s+Office:|$)', line)
            if primary_match:
                current_payor_primary = primary_match.group(1).strip()

            
            # Extract Secondary payor only if it exists
            if "Secondary:" in line:
                secondary_match = re.search(r'Secondary:([^\s]+(?:\s+[^\s]+)*?)(?:\s+Office:|$)', line)
                if secondary_match:
                    current_payor_secondary = secondary_match.group(1).strip()

            
            i += 1
            continue
            
        # Parse data lines - look for date pattern
        if re.match(r'^\d{2}/\d{2}/\d{4}', line):
            # Check if next line continues this entry
            combined_line = line
            j = i + 1
            while j < len(lines):
                next_line = lines[j]
                if (re.match(r'^\d{2}/\d{2}/\d{4}', next_line) or 
                    "Payor:" in next_line or
                    any(word in next_line.upper() for word in ["UNPAID CHARGES", "FILTER:", "PRINTED ON:", "PAGE #:", "TOTAL UNITS:", "TOTAL CHARGES:"]) or
                    ("Date" in next_line and ("Patient" in next_line or "Code" in next_line))):
                    break
                combined_line += " " + next_line
                j += 1
            
            i = j - 1
            tokens = combined_line.split()
            
            if len(tokens) >= 3:
                try:
                    date = tokens[0]
                    patient_num = tokens[1] if len(tokens) > 1 else ""
                    
                    # Find key elements first
                    code_idx = -1
                    amount_indices = []
                    units_idx = -1
                    
                    # Find 5-digit code
                    for idx in range(len(tokens)):
                        if re.match(r'^\d{5}$', tokens[idx]):
                            code_idx = idx
                            break
                    
                    # Find all amounts (decimal numbers)
                    for idx in range(len(tokens)):
                        if re.match(r'^\d+\.\d{2}$', tokens[idx]):
                            amount_indices.append(idx)
                    
                    # Find units (1-2 digit number before last amount)
                    if len(amount_indices) > 0:
                        last_amount_idx = amount_indices[-1]
                        for idx in range(last_amount_idx-1, -1, -1):
                            if re.match(r'^\d{1,2}$', tokens[idx]):
                                units_idx = idx
                                break
                    
                    if code_idx == -1:
                        continue
                    
                    # Code
                    code = tokens[code_idx]
                    
                    # Find single letter (usually 'A') between clinician and patient name
                    single_letter_idx = -1
                    if len(amount_indices) > 0 and units_idx > 0:
                        first_amount_idx = amount_indices[0]
                        for idx in range(first_amount_idx + 1, units_idx):
                            if idx < len(tokens) and len(tokens[idx]) == 1 and tokens[idx].isalpha():
                                single_letter_idx = idx
                                break
                    
                    # Clinician - between first amount and single letter
                    clinician = ""
                    if len(amount_indices) > 0 and single_letter_idx > 0:
                        first_amount_idx = amount_indices[0]
                        clinician_parts = []
                        for idx in range(first_amount_idx + 1, single_letter_idx):
                            if idx < len(tokens):
                                clinician_parts.append(tokens[idx])
                        clinician = ' '.join(clinician_parts)
                    
                    # Patient Name - between single letter and units
                    patient_name = ""
                    if single_letter_idx > 0 and units_idx > 0:
                        name_parts = []
                        for idx in range(single_letter_idx + 1, units_idx):
                            if idx < len(tokens):
                                name_parts.append(tokens[idx])
                        full_name = ' '.join(name_parts).rstrip(',')
                        
                        # Remove single alphabetic characters at the beginning
                        name_tokens = full_name.split()
                        while name_tokens and len(name_tokens[0]) == 1 and name_tokens[0].isalpha():
                            name_tokens.pop(0)
                        patient_name = ' '.join(name_tokens)
                    
                    # Units
                    units = tokens[units_idx] if units_idx > 0 else ""
                    
                    # Description - between code and first amount
                    description = ""
                    if len(amount_indices) > 0:
                        first_amount_idx = amount_indices[0]
                        if code_idx + 1 < first_amount_idx:
                            description = ' '.join(tokens[code_idx+1:first_amount_idx])
                    
                    # Amounts
                    amount = float(tokens[amount_indices[0]]) if len(amount_indices) > 0 else 0.0
                    balance = float(tokens[amount_indices[1]]) if len(amount_indices) > 1 else amount
                    
                    # Account Type - after units
                    account_type = ""
                    if units_idx > 0 and units_idx + 1 < len(tokens):
                        remaining = tokens[units_idx+1:]
                        filtered_remaining = []
                        for token in remaining:
                            if not re.match(r'^\d+\.\d{2}$', token):
                                filtered_remaining.append(token)
                        account_type = ' '.join(filtered_remaining)
                    
                    record = {
                        'Date': date,
                        'Patient #': patient_num,
                        'Patient Name': patient_name,
                        'Code': code,
                        'Units': units,
                        'Description': description,
                        'Amount': amount,
                        'Balance': balance,
                        'Clinician': clinician,
                        'Account Type': account_type,
                        'Payor Primary': current_payor_primary,
                        'Payor Secondary': current_payor_secondary
                    }
                    charges_data.append(record)
                    
                except (ValueError, IndexError):
                    pass
        
        i += 1
    

    
    return charges_data

def create_xlsx_file(charges_data, output_path):
    columns = ['Date', 'Patient #', 'Patient Name', 'Code', 'Units', 'Description', 
               'Amount', 'Balance', 'Clinician', 'Account Type', 'Payor Primary', 'Payor Secondary']
    df = pd.DataFrame(charges_data, columns=columns)
    
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Unpaid Charges', index=False)
        
        workbook = writer.book
        worksheet = writer.sheets['Unpaid Charges']
        header_font = Font(bold=True)
        header_alignment = Alignment(horizontal='center')
        
        for col_num, column_title in enumerate(df.columns, 1):
            cell = worksheet.cell(row=1, column=col_num)
            cell.font = header_font
            cell.alignment = header_alignment
        
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            worksheet.column_dimensions[column_letter].width = adjusted_width