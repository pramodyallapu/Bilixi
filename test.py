import pandas as pd
from typing import Dict, List
import numpy as np
from main import extract_text_from_pdf, parse_insurance_claims
import re


def compare_excel_get_all_differences(
    file1_path: str,
    file2_path: str,
    claim_amount_col: str = "Claim Amount",
    sheet_name: str = None,
    output_file: str = None
) -> Dict:
    """
    Compare two Excel files and return ALL different rows from both files.

    Args:
        file1_path (str): Path to first Excel file
        file2_path (str): Path to second Excel file
        claim_amount_col (str): Column name containing claim amounts
        sheet_name (str): Sheet name to read (if None, reads first sheet)
        output_file (str): Optional path to save comparison results

    Returns:
        Dict: Contains all different rows from both files
    """

    try:
        # Read Excel files
        if sheet_name:
            df1 = pd.read_excel(file1_path, sheet_name=sheet_name)
            df2 = pd.read_excel(file2_path, sheet_name=sheet_name)
        else:
            df1 = pd.read_excel(file1_path)
            df2 = pd.read_excel(file2_path)

        # Ensure claim amount column exists
        if claim_amount_col not in df1.columns:
            raise ValueError(f"Column '{claim_amount_col}' not found in first file")
        if claim_amount_col not in df2.columns:
            raise ValueError(f"Column '{claim_amount_col}' not found in second file")

        # Add original row numbers (Excel-style, starting from 2)
        df1 = df1.reset_index(drop=True)
        df2 = df2.reset_index(drop=True)
        df1['Excel_Row'] = df1.index + 2
        df2['Excel_Row'] = df2.index + 2

        # Get minimum number of rows to compare
        min_rows = min(len(df1), len(df2))

        # Lists to store different rows
        different_rows_file1 = []
        different_rows_file2 = []
        comparison_details = []

        # Compare row by row
        for i in range(min_rows):
            amount1 = df1.loc[i, claim_amount_col]
            amount2 = df2.loc[i, claim_amount_col]

            # Handle comparison with tolerance for floating point numbers
            if pd.isna(amount1) and pd.isna(amount2):
                are_same = True
            elif pd.isna(amount1) or pd.isna(amount2):
                are_same = False
            else:
                # Convert to float and compare with tolerance
                try:
                    amount1_float = float(amount1)
                    amount2_float = float(amount2)
                    are_same = abs(amount1_float - amount2_float) < 0.001
                except (ValueError, TypeError):
                    are_same = str(amount1) == str(amount2)

            if not are_same:
                # Get entire row data for both files
                row1_data = df1.iloc[i].to_dict()
                row2_data = df2.iloc[i].to_dict()

                different_rows_file1.append(row1_data)
                different_rows_file2.append(row2_data)

                comparison_details.append({
                    'Row_Number_File1': df1.loc[i, 'Excel_Row'],
                    'Row_Number_File2': df2.loc[i, 'Excel_Row'],
                    'Claim_Amount_File1': amount1,
                    'Claim_Amount_File2': amount2,
                    'Are_Same': are_same
                })

        # Handle extra rows (rows that exist in one file but not the other)
        extra_rows_file1 = []
        extra_rows_file2 = []

        if len(df1) > len(df2):
            extra_rows = df1.iloc[min_rows:]
            for _, row in extra_rows.iterrows():
                extra_rows_file1.append(row.to_dict())

        if len(df2) > len(df1):
            extra_rows = df2.iloc[min_rows:]
            for _, row in extra_rows.iterrows():
                extra_rows_file2.append(row.to_dict())

        # Combine all different rows (mismatched + extra rows)
        all_different_file1 = different_rows_file1 + extra_rows_file1
        all_different_file2 = different_rows_file2 + extra_rows_file2

        # Create summary
        total_different = len(all_different_file1) + len(all_different_file2)

        summary = {
            'Total_Rows_File1': len(df1),
            'Total_Rows_File2': len(df2),
            'Rows_Compared': min_rows,
            'Matching_Rows': min_rows - len(different_rows_file1),
            'Different_Rows_Count': len(different_rows_file1),
            'Extra_Rows_File1_Count': len(extra_rows_file1),
            'Extra_Rows_File2_Count': len(extra_rows_file2),
            'Total_Different_Rows': total_different,
            'Match_Percentage': ((min_rows - len(different_rows_file1)) / min_rows * 100) if min_rows > 0 else 0
        }

        # Prepare final result
        result = {
            'summary': summary,
            'all_different_rows_file1': all_different_file1,
            'all_different_rows_file2': all_different_file2,
            'comparison_details': comparison_details,
            'extra_rows_file1': extra_rows_file1,
            'extra_rows_file2': extra_rows_file2
        }

        # Save to Excel if output file specified
        if output_file:
            save_all_differences_to_excel(result, output_file)

        return result

    except Exception as e:
        print(f"Error comparing Excel files: {e}")
        return {'error': str(e)}

def save_all_differences_to_excel(results: Dict, output_path: str):
    """Save all different rows to Excel file with multiple sheets"""
    try:
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # Summary sheet
            summary_df = pd.DataFrame([results['summary']])
            summary_df.to_excel(writer, sheet_name='Summary', index=False)

            # All different rows from File1
            if results['all_different_rows_file1']:
                diff1_df = pd.DataFrame(results['all_different_rows_file1'])
                diff1_df.to_excel(writer, sheet_name='Different_Rows_File1', index=False)

            # All different rows from File2
            if results['all_different_rows_file2']:
                diff2_df = pd.DataFrame(results['all_different_rows_file2'])
                diff2_df.to_excel(writer, sheet_name='Different_Rows_File2', index=False)

            # Comparison details
            if results['comparison_details']:
                comp_df = pd.DataFrame(results['comparison_details'])
                comp_df.to_excel(writer, sheet_name='Comparison_Details', index=False)

            # Extra rows
            if results['extra_rows_file1']:
                extra1_df = pd.DataFrame(results['extra_rows_file1'])
                extra1_df.to_excel(writer, sheet_name='Extra_Rows_File1', index=False)

            if results['extra_rows_file2']:
                extra2_df = pd.DataFrame(results['extra_rows_file2'])
                extra2_df.to_excel(writer, sheet_name='Extra_Rows_File2', index=False)

        print(f"All differences saved to: {output_path}")

    except Exception as e:
        print(f"Error saving results: {e}")

def compare_pdf_to_excel(
    pdf_path: str,
    excel_path: str,
    sheet_name: str = None,
    output_file: str = None,
    key_fields: list = None,
) -> Dict:
    """
    Compare claims parsed from a PDF with the rows in a generated Excel file.
    Identifies rows that were skipped (present in PDF but missing in Excel),
    extra rows (present in Excel but not in PDF), and value mismatches for
    common rows. Optionally saves a detailed multi-sheet Excel report.

    Args:
        pdf_path: Path to the source PDF
        excel_path: Path to the processed Excel created from the PDF
        sheet_name: Sheet name to read from excel (default first sheet)
        output_file: Optional path to save a detailed comparison report as xlsx
        key_fields: Optional list of fields to build the identity key for rows.
                    Defaults to ['Account','Patient Name','DOS','Insurance Company','Claim Amount','Insurance ID']

    Returns:
        Dict containing summary and detailed differences.
    """
    # Helpers for normalization
    def norm_str(v):
        if pd.isna(v):
            return ''
        return str(v).strip().lower()

    def norm_amount(v):
        try:
            return float(str(v).replace(',', ''))
        except Exception:
            return np.nan

    def norm_date(v):
        if pd.isna(v) or v == '':
            return ''
        try:
            # Try common formats; pandas will handle most cases
            dt = pd.to_datetime(v, errors='coerce', dayfirst=False)
            if pd.isna(dt):
                return str(v)
            return dt.strftime('%m/%d/%y')
        except Exception:
            return str(v)

    def build_key(row, fields):
        parts = []
        for f in fields:
            val = row.get(f, '')
            if f in ['Claim Amount', 'Over Due']:
                parts.append(f"{norm_amount(val):.2f}" if not pd.isna(norm_amount(val)) else '')
            elif f == 'DOS':
                parts.append(norm_date(val))
            else:
                parts.append(norm_str(val))
        return '|'.join(parts)

    try:
        # 1) Parse PDF into a DataFrame
        text_content = extract_text_from_pdf(pdf_path)
        claims = parse_insurance_claims(text_content)
        pdf_df = pd.DataFrame(claims)
        if pdf_df.empty:
            raise ValueError('No claims parsed from the PDF')
        # Add source row numbers (Excel-style, header at row 1)
        pdf_df = pdf_df.reset_index(drop=True)
        pdf_df['PDF_Row'] = pdf_df.index + 2

        # 2) Read Excel into a DataFrame
        excel_df = pd.read_excel(excel_path, sheet_name=sheet_name) if sheet_name else pd.read_excel(excel_path)
        if excel_df.empty:
            raise ValueError('Processed Excel has no rows')
        excel_df = excel_df.reset_index(drop=True)
        excel_df['Excel_Row'] = excel_df.index + 2

        # 3) Ensure consistent column names
        expected_cols = ['Account', 'Patient Name', 'DOS', 'Insurance Company', 'Claim Amount', 'Over Due', 'Insurance ID']
        for col in expected_cols:
            if col not in pdf_df.columns:
                pdf_df[col] = ''
            if col not in excel_df.columns:
                excel_df[col] = ''

        # 4) Keys for matching
        if key_fields is None:
            key_fields = ['Account', 'Patient Name', 'DOS', 'Insurance Company', 'Claim Amount', 'Insurance ID']

        pdf_df['__key__'] = pdf_df.apply(lambda r: build_key(r, key_fields), axis=1)
        excel_df['__key__'] = excel_df.apply(lambda r: build_key(r, key_fields), axis=1)

        pdf_keys = set(pdf_df['__key__'])
        excel_keys = set(excel_df['__key__'])

        missing_keys = sorted(list(pdf_keys - excel_keys))  # present in PDF, missing in Excel (skipped)
        extra_keys = sorted(list(excel_keys - pdf_keys))    # present in Excel only
        common_keys = sorted(list(pdf_keys & excel_keys))

        missing_in_excel = pdf_df[pdf_df['__key__'].isin(missing_keys)].copy()
        extra_in_excel = excel_df[excel_df['__key__'].isin(extra_keys)].copy()

        # 5) Compare common rows for value mismatches
        mismatches = []
        mismatch_rows = []
        for k in common_keys:
            p_row = pdf_df[pdf_df['__key__'] == k].iloc[0]
            e_row = excel_df[excel_df['__key__'] == k].iloc[0]
            row_diff = {'Key': k, 'PDF_Row': int(p_row['PDF_Row']), 'Excel_Row': int(e_row['Excel_Row'])}
            has_diff = False
            for col in expected_cols:
                p_val, e_val = p_row.get(col, ''), e_row.get(col, '')
                # Normalize for fair comparison
                if col in ['Claim Amount', 'Over Due']:
                    p_cmp = norm_amount(p_val)
                    e_cmp = norm_amount(e_val)
                    same = (pd.isna(p_cmp) and pd.isna(e_cmp)) or (not pd.isna(p_cmp) and not pd.isna(e_cmp) and abs(p_cmp - e_cmp) < 0.01)
                elif col == 'DOS':
                    p_cmp = norm_date(p_val)
                    e_cmp = norm_date(e_val)
                    same = p_cmp == e_cmp
                else:
                    p_cmp = norm_str(p_val)
                    e_cmp = norm_str(e_val)
                    same = p_cmp == e_cmp
                if not same:
                    has_diff = True
                    row_diff[f'{col} (PDF)'] = p_val
                    row_diff[f'{col} (Excel)'] = e_val
            if has_diff:
                mismatches.append(row_diff)
                mismatch_rows.append({'PDF_Row': int(p_row['PDF_Row']), 'Excel_Row': int(e_row['Excel_Row']), 'Key': k})

        # 6) Build summary
        summary = {
            'PDF_Total_Rows': int(len(pdf_df)),
            'Excel_Total_Rows': int(len(excel_df)),
            'Common_Rows_By_Key': int(len(common_keys)),
            'Missing_in_Excel': int(len(missing_in_excel)),
            'Extra_in_Excel': int(len(extra_in_excel)),
            'Value_Mismatch_Rows': int(len(mismatches)),
        }

        results = {
            'summary': summary,
            'missing_in_excel': missing_in_excel[expected_cols + ['PDF_Row', '__key__']].to_dict(orient='records'),
            'extra_in_excel': extra_in_excel[expected_cols + ['Excel_Row', '__key__']].to_dict(orient='records'),
            'value_mismatches': mismatches,
            'key_fields': key_fields,
        }

        if output_file:
            save_pdf_excel_comparison_to_excel(results, output_file)

        return results

    except Exception as e:
        return {'error': str(e)}


def save_pdf_excel_comparison_to_excel(results: Dict, output_path: str):
    """Save PDF vs Excel comparison into a multi-sheet Excel workbook."""
    try:
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # Summary
            pd.DataFrame([results['summary']]).to_excel(writer, sheet_name='Summary', index=False)

            # Missing in Excel (skipped rows)
            miss = results.get('missing_in_excel', [])
            if miss:
                pd.DataFrame(miss).to_excel(writer, sheet_name='Missing_in_Excel', index=False)

            # Extra in Excel
            extra = results.get('extra_in_excel', [])
            if extra:
                pd.DataFrame(extra).to_excel(writer, sheet_name='Extra_in_Excel', index=False)

            # Value mismatches
            mism = results.get('value_mismatches', [])
            if mism:
                pd.DataFrame(mism).to_excel(writer, sheet_name='Value_Mismatches', index=False)

        print(f"PDF vs Excel comparison saved to: {output_path}")
    except Exception as e:
        print(f"Error saving results: {e}")


# --- Parsing audit helpers ---

def parse_insurance_claims_with_trace(text_content):
    import re
    claims_data = []
    audit_rows = []
    lines = [line.strip() for line in text_content.split('\n') if line.strip()]
    current_account = ""
    current_patient = ""

    for idx, line in enumerate(lines):
        # Skip header/footer lines
        if any(word in line for word in [
            "Murphy", "Page:", "Overdue", "Unpaid", "Insurance", "Report Date", "System:", "Time:", "Run:"
        ]):
            audit_rows.append({
                'Line_No': idx + 1,
                'Line_Text': line,
                'Status': 'Header/Footer skipped',
                'Reason': 'Header/Footer indicator'
            })
            continue

        # Check if line starts with account and patient name
        m = re.match(r"^([A-Z]{3,}\d*X?)\s+([A-Z][A-Za-z\.\'\s]+)", line)
        if m:
            current_account = m.group(1)
            current_patient = m.group(2).strip()
            rest = line[m.end():].strip()
            status_prefix = 'New claim context'
        else:
            if current_account and current_patient:
                rest = line.strip()
                status_prefix = 'Continuation'
            else:
                audit_rows.append({
                    'Line_No': idx + 1,
                    'Line_Text': line,
                    'Status': 'Skipped',
                    'Reason': 'No claim context and no account/patient match'
                })
                continue

        tokens = rest.split()
        if len(tokens) < 3:
            audit_rows.append({
                'Line_No': idx + 1,
                'Line_Text': line,
                'Status': 'Skipped',
                'Reason': 'Insufficient tokens after context'
            })
            continue

        dos = ''
        insurance = ''
        claim_amount = ''
        over_due = ''
        insurance_id = ''

        # Find all dates
        date_indices = [t_i for t_i, tok in enumerate(tokens) if re.match(r'\d{2}/\d{2}/\d{2}', tok)]
        dates = [tokens[t_i] for t_i in date_indices]

        if len(dates) >= 3:
            dos = dates[2]
        elif len(dates) >= 1:
            dos = dates[-1]

        if not dos:
            audit_rows.append({
                'Line_No': idx + 1,
                'Line_Text': line,
                'Status': 'Skipped',
                'Reason': 'No DOS date found'
            })
            continue

        i = date_indices[-1] + 1 if date_indices else 0

        # Collect insurance name until Pri/Sec/Oth
        insurance_parts = []
        while i < len(tokens) and tokens[i] not in ['Pri', 'Sec', 'Oth']:
            insurance_parts.append(tokens[i])
            i += 1
        insurance = ' '.join(insurance_parts)

        # Skip Pri/Sec/Oth and E/W/P/F/H indicators
        if i < len(tokens) and tokens[i] in ['Pri', 'Sec', 'Oth']:
            i += 1
        if i < len(tokens) and tokens[i] in ['E', 'W', 'P', 'F', 'H']:
            i += 1

        # Claim amount
        if i < len(tokens):
            try:
                claim_amount = float(tokens[i].replace(',', ''))
                i += 1
            except Exception:
                pass

        # Status words
        status_words = ['Hold', 'WtERA', 'Forwd', 'Paid', 'Denied', 'Rej', 'Reversed', 'Recoup', 'Offset']
        if i < len(tokens) and tokens[i] in status_words:
            i += 1

        # Over due
        if i < len(tokens):
            try:
                over_due = float(tokens[i].replace(',', ''))
                i += 1
            except Exception:
                pass

        # Insurance ID
        if i < len(tokens):
            insurance_id = ' '.join(tokens[i:])
            m_id = re.match(r'([A-Za-z0-9\-\_]+)', insurance_id)
            if m_id:
                insurance_id = m_id.group(1)

        if dos and insurance and claim_amount != '':
            claims_data.append({
                'Account': current_account,
                'Patient Name': current_patient,
                'DOS': dos,
                'Insurance Company': insurance,
                'Claim Amount': claim_amount,
                'Over Due': over_due,
                'Insurance ID': insurance_id,
                'PDF_Row': idx + 2
            })
            audit_rows.append({
                'Line_No': idx + 1,
                'Line_Text': line,
                'Status': f'{status_prefix}: Claim recorded',
                'Reason': ''
            })
        else:
            audit_rows.append({
                'Line_No': idx + 1,
                'Line_Text': line,
                'Status': 'Skipped',
                'Reason': 'Missing essential fields (DOS/Insurance/Claim Amount)'
            })

    return claims_data, audit_rows


def audit_pdf_parsing(pdf_path: str, output_file: str = None):
    """
    Produce a line-by-line audit of the PDF parsing, indicating which lines
    created claim rows and which were skipped (with reasons). Optionally saves
    to an Excel file with Line_Audit and Parsed_Claims sheets.
    """
    text_content = extract_text_from_pdf(pdf_path)
    claims_data, audit_rows = parse_insurance_claims_with_trace(text_content)

    audit_df = pd.DataFrame(audit_rows)
    claims_df = pd.DataFrame(claims_data)

    if output_file:
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            audit_df.to_excel(writer, sheet_name='Line_Audit', index=False)
            if not claims_df.empty:
                claims_df.to_excel(writer, sheet_name='Parsed_Claims', index=False)
        print(f"Parsing audit saved to: {output_file}")

    return {'audit': audit_rows, 'claims': claims_data}

def print_detailed_differences(results: Dict):
    """Print detailed information about differences"""
    summary = results['summary']

    print("\n" + "=" * 60)
    print("DETAILED DIFFERENCE ANALYSIS")
    print("=" * 60)
    print(f"File 1 total rows: {summary['Total_Rows_File1']}")
    print(f"File 2 total rows: {summary['Total_Rows_File2']}")
    print(f"Rows compared: {summary['Rows_Compared']}")
    print(f"Matching rows: {summary['Matching_Rows']}")
    print(f"Different rows (mismatched values): {summary['Different_Rows_Count']}")
    print(f"Extra rows in File 1: {summary['Extra_Rows_File1_Count']}")
    print(f"Extra rows in File 2: {summary['Extra_Rows_File2_Count']}")
    print(f"Total different rows: {summary['Total_Different_Rows']}")
    print(f"Match percentage: {summary['Match_Percentage']:.2f}%")

    # Show sample of different rows
    if results['all_different_rows_file1']:
        print(f"\nFirst 5 different rows from File 1:")
        for i, row in enumerate(results['all_different_rows_file1'][:5]):
            print(f"Row {row['Excel_Row']}: Claim Amount = {row.get('Claim Amount', 'N/A')}")

    if results['all_different_rows_file2']:
        print(f"\nFirst 5 different rows from File 2:")
        for i, row in enumerate(results['all_different_rows_file2'][:5]):
            print(f"Row {row['Excel_Row']}: Claim Amount = {row.get('Claim Amount', 'N/A')}")

# Example usage
if __name__ == "__main__":
    # Compare PDF vs processed Excel and write a detailed report
    results = compare_pdf_to_excel(
        pdf_path="Murphy bioloxi report - 082020255.pdf",
        excel_path="Murphy bioloxi report - 082020255_processed.xlsx",
        output_file="pdf_vs_excel_report.xlsx"
    )

    if 'error' in results:
        print("Error:", results['error'])
    else:
        summary = results['summary']
        print("PDF vs Excel Comparison Summary:")
        print(summary)
        print(f"Missing in Excel (skipped rows): {summary['Missing_in_Excel']}")
        print(f"Extra in Excel: {summary['Extra_in_Excel']}")
        print(f"Value mismatch rows: {summary['Value_Mismatch_Rows']}")
        print("Detailed report saved to: pdf_vs_excel_report.xlsx")

