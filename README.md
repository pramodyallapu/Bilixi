# PDF to Excel Converter

This application automatically converts Biloxi insurance PDF files to Excel format with proper data extraction and formatting.

## Features

- **Web Interface**: Easy-to-use drag-and-drop web interface
- **Automatic Parsing**: Extracts insurance claim data from PDF files
- **Excel Output**: Creates properly formatted Excel files with columns:
  - Account No
  - Patient Name
  - Insurance
  - DOS (Date of Service)
  - Insurance ID
  - Claim Amount
  - Over Due

## Installation

1. Make sure you have Python 3.7+ installed
2. Install required packages:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### Web Interface (Recommended)

1. Start the web server:
   ```bash
   python run_server.py
   ```
   Or:
   ```bash
   python main.py web
   ```

2. Open your browser and go to: `http://localhost:8000`

3. Upload your PDF file using the web interface:
   - Drag and drop your PDF file onto the upload area
   - Or click "Choose File" to select a file
   - Click "Convert to Excel" to process the file
   - Download the resulting Excel file

### Command Line Usage

You can also use the converter from the command line:

```bash
# Convert a specific PDF file
python main.py "xxxxxxxxxxxxx.pdf"

# Convert with custom output filename
python main.py "xxxxxxxxxxxxxxxx.pdf" "xxxxxxxxxxxxxxxxx.xlsx"
```

## File Structure

- `main.py` - Main application with PDF parsing and web interface
- `run_server.py` - Simple script to start the web server
- `requirements.txt` - Python dependencies
- `downloads/` - Directory where converted Excel files are stored (created automatically)

## Supported PDF Format

The application is designed to parse Biloxi insurance PDF files with the following format:
- Account numbers and patient names
- Date of service information
- Insurance company names (Blue Cross, Humana, Aetna, etc.)
- Claim amounts and overdue information
- Insurance ID numbers

## Output Format

The Excel file will contain the following columns:
- **Account No**: Patient account number
- **Patient Name**: Full patient name
- **Insurance**: Insurance company name
- **DOS**: Date of service (YYYY-MM-DD format)
- **Insurance ID**: Insurance identification number
- **Claim Amount**: Claim amount in dollars
- **Over Due**: Number of overdue days

## Troubleshooting

1. **PDF not processing**: Make sure the PDF contains text (not just images)
2. **No data extracted**: Verify the PDF follows the expected Biloxi format
3. **Web server not starting**: Check if port 8000 is available
4. **File download issues**: Check the `downloads/` directory permissions

## Technical Details

- Built with FastAPI for the web interface
- Uses pdfplumber for PDF text extraction
- Uses pandas and openpyxl for Excel file creation
- Includes comprehensive error handling and logging

## Example

Input PDF: `xxxxxxxxxxxxxxxxxx.pdf`
Output Excel: `xxxxxxxxxxxxxxxxxxx.xlsx`

The application automatically converts "Biloxi" to "Bilxy" in the output filename to match your naming convention.
"# bilxy" 
