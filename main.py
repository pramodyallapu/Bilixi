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

# Import parsing functions from separate modules
import biloxy_parse
import paul_parse
import unpaid_charges_parse

app = FastAPI()

def determine_file_type(filename):
    """Determine file type based on filename"""
    filename_lower = filename.lower()
    if 'paul' in filename_lower:
        return 'paul'
    elif 'biloxi' in filename_lower or 'bilxy' in filename_lower:
        return 'biloxi'
    else:
        # Default to biloxi if unclear
        return 'biloxi'



@app.get("/", response_class=HTMLResponse)
async def read_root():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
    <title>PDF to Excel Converter</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet"/>
    </head>
    <body class="bg-gradient-to-br from-gray-100 to-gray-200 min-h-screen flex items-center justify-center p-6">
    <div class="w-full max-w-3xl bg-white rounded-2xl shadow-lg overflow-hidden">
        
        <!-- Header -->
        <header class="bg-gradient-to-r from-indigo-600 to-purple-600 text-white text-center p-8">
        <h1 class="text-2xl md:text-3xl font-bold flex justify-center items-center gap-3">
            <i class="fas fa-file-excel"></i> PDF to Excel Converter
        </h1>
        <p class="mt-2 opacity-90">Convert Insurance Claims PDF to Excel in seconds</p>
        </header>

        <!-- Content -->
        <div class="p-6 space-y-6">
        
        <!-- Upload Card -->
        <div class="bg-gray-50 rounded-xl p-6 shadow-sm">
            <h2 class="text-indigo-600 text-lg font-semibold flex items-center gap-2">
            <i class="fas fa-upload"></i> Upload PDF File
            </h2>
            <p class="text-gray-600 text-sm mt-1">Drag & drop or browse to upload your claims PDF</p>
            
            <div id="dropArea" class="mt-4 border-2 border-dashed border-gray-300 rounded-xl p-10 text-center cursor-pointer hover:border-indigo-500 hover:bg-indigo-50 transition">
            <i class="fas fa-cloud-upload-alt text-4xl text-indigo-500"></i>
            <p class="mt-2 text-gray-600">Drag & drop PDF here or <span class="text-indigo-600 font-semibold">Browse</span></p>
            <input type="file" id="pdfFile" name="file" accept=".pdf" class="hidden"/>
            </div>

            <!-- File Info -->
            <div id="fileInfo" class="hidden mt-4 flex items-center gap-3 bg-white border-l-4 border-indigo-500 rounded-lg p-3 shadow">
            <i class="fas fa-file-pdf text-indigo-500 text-2xl"></i>
            <div class="flex-1">
                <p id="fileName" class="font-semibold">document.pdf</p>
                <p id="fileSize" class="text-sm text-gray-500">0 KB</p>
            </div>
            <button id="removeFile" class="text-gray-400 hover:text-red-500 transition">
                <i class="fas fa-times"></i>
            </button>
            </div>

            <!-- Convert Buttons -->
            <button id="convertBtn" disabled class="mt-4 w-full bg-indigo-600 text-white py-3 rounded-full font-semibold shadow-md hover:bg-indigo-700 transition flex justify-center items-center gap-2">
            <i class="fas fa-sync-alt"></i> Convert to Excel
            </button>
            
            <button id="convertUnpaidBtn" disabled class="mt-2 w-full bg-green-600 text-white py-3 rounded-full font-semibold shadow-md hover:bg-green-700 transition flex justify-center items-center gap-2">
            <i class="fas fa-file-invoice-dollar"></i> Convert Unpaid Charges
            </button>

            <!-- Progress -->
            <div id="progressContainer" class="hidden mt-4">
            <div class="w-full bg-gray-200 rounded-full h-2">
                <div id="progressBar" class="bg-gradient-to-r from-indigo-600 to-purple-600 h-2 rounded-full w-0"></div>
            </div>
            <p id="progressText" class="text-center text-sm text-gray-600 mt-2">Processing... 0%</p>
            </div>

            <!-- Result -->
            <div id="result" class="hidden mt-4 p-4 rounded-lg shadow text-sm"></div>
        </div>

        <!-- Features -->
        <div>
            <h2 class="text-indigo-600 text-lg font-semibold flex items-center gap-2">
            <i class="fas fa-star"></i> Why Choose Us
            </h2>
            <div class="grid md:grid-cols-3 gap-6 mt-4">
            <div class="flex gap-3">
                <i class="fas fa-shield-alt bg-indigo-600 text-white w-10 h-10 flex items-center justify-center rounded-full"></i>
                <div>
                <h3 class="font-semibold">Secure</h3>
                <p class="text-sm text-gray-600">Your files are processed safely, never stored.</p>
                </div>
            </div>
            <div class="flex gap-3">
                <i class="fas fa-bolt bg-indigo-600 text-white w-10 h-10 flex items-center justify-center rounded-full"></i>
                <div>
                <h3 class="font-semibold">Fast</h3>
                <p class="text-sm text-gray-600">Quick conversion even for large PDFs.</p>
                </div>
            </div>
            <div class="flex gap-3">
                <i class="fas fa-chart-line bg-indigo-600 text-white w-10 h-10 flex items-center justify-center rounded-full"></i>
                <div>
                <h3 class="font-semibold">Accurate</h3>
                <p class="text-sm text-gray-600">Precise table recognition keeps your data intact.</p>
                </div>
            </div>
            </div>
        </div>
        </div>

        <!-- Footer -->
        <footer class="text-center text-gray-500 text-sm p-4 border-t">© 2025 PDF(Biloxi) to Excel Converter</footer>
    </div>

    <!-- JS (same logic) -->
    <script>
        document.addEventListener('DOMContentLoaded', () => {
        const dropArea = document.getElementById('dropArea');
        const fileInput = document.getElementById('pdfFile');
        const fileInfo = document.getElementById('fileInfo');
        const fileName = document.getElementById('fileName');
        const fileSize = document.getElementById('fileSize');
        const removeFile = document.getElementById('removeFile');
        const convertBtn = document.getElementById('convertBtn');
        const convertUnpaidBtn = document.getElementById('convertUnpaidBtn');
        const result = document.getElementById('result');
        const progressContainer = document.getElementById('progressContainer');
        const progressBar = document.getElementById('progressBar');
        const progressText = document.getElementById('progressText');
        
        let selectedFile = null;

        dropArea.addEventListener('click', () => fileInput.click());
        ['dragenter','dragover','dragleave','drop'].forEach(e => {
            dropArea.addEventListener(e, ev => {ev.preventDefault(); ev.stopPropagation();});
        });
        dropArea.addEventListener('drop', e => handleFiles(e.dataTransfer.files[0]));
        fileInput.addEventListener('change', () => fileInput.files[0] && handleFiles(fileInput.files[0]));
        removeFile.addEventListener('click', e => {e.stopPropagation(); resetFile();});
        convertBtn.addEventListener('click', convertFile);
        convertUnpaidBtn.addEventListener('click', convertUnpaidFile);

        function handleFiles(file) {
            if (file.type !== 'application/pdf') return showResult('Please select a PDF file.', 'bg-red-100 text-red-600');
            selectedFile = file;
            fileName.textContent = file.name;
            fileSize.textContent = formatSize(file.size);
            fileInfo.classList.remove('hidden');
            convertBtn.disabled = false;
            convertUnpaidBtn.disabled = false;
            result.classList.add('hidden');
        }

        function resetFile() {
            selectedFile = null;
            fileInput.value = '';
            fileInfo.classList.add('hidden');
            convertBtn.disabled = true;
            convertUnpaidBtn.disabled = true;
            progressContainer.classList.add('hidden');
            result.classList.add('hidden');
        }

        function formatSize(bytes) {
            const sizes = ['Bytes','KB','MB','GB'];
            if (bytes === 0) return '0 Bytes';
            const i = Math.floor(Math.log(bytes)/Math.log(1024));
            return (bytes/Math.pow(1024,i)).toFixed(2)+' '+sizes[i];
        }

        function simulateProgress(cb) {
            let p = 0; progressContainer.classList.remove('hidden');
            const interval = setInterval(() => {
            p+=Math.random()*15;
            if(p>=100){p=100; clearInterval(interval); cb();}
            progressBar.style.width=p+'%';
            progressText.textContent=`Processing... ${Math.round(p)}%`;
            },300);
        }

        function convertFile() {
            processFile('/upload/', 'insurance_claims.xlsx', 'Insurance Claims');
        }
        
        function convertUnpaidFile() {
            processFile('/upload-unpaid/', 'unpaid_charges.xlsx', 'Unpaid Charges');
        }
        
        function processFile(endpoint, defaultFilename, type) {
            if(!selectedFile) return showResult('Please select a file.', 'bg-red-100 text-red-600');
            const formData=new FormData(); formData.append('file',selectedFile);
            simulateProgress(()=>{
            fetch(endpoint,{method:'POST',body:formData})
            .then(r=>r.ok?r.blob():Promise.reject('Conversion failed'))
            .then(blob=>{
                const url=URL.createObjectURL(blob);
                const a=document.createElement('a');
                a.href=url; a.download=defaultFilename; a.click();
                URL.revokeObjectURL(url);
                showResult(`✅ ${selectedFile.name} converted to ${type} successfully.`, 'bg-green-100 text-green-600');
                progressContainer.classList.add('hidden');
            })
            .catch(err=>{
                progressContainer.classList.add('hidden');
                showResult('Error: '+err,'bg-red-100 text-red-600');
            });
            });
        }

        function showResult(msg, style) {
            result.className=`mt-4 p-4 rounded-lg shadow text-sm ${style}`;
            result.textContent=msg;
            result.classList.remove('hidden');
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

        # Determine file type and use appropriate parser
        file_type = determine_file_type(file.filename)
        print(f"Detected file type: {file_type} for filename: {file.filename}")
        
        if file_type == 'paul':
            # Use Paul parser
            text_content = paul_parse.extract_text_from_pdf(temp_pdf_path)
            if not text_content.strip():
                raise HTTPException(status_code=400, detail="No text extracted from PDF")
            claims_data, pattern_missed_data = paul_parse.parse_insurance_claims_with_fallback(text_content, temp_pdf_path)
        else:
            # Use Biloxi parser (default)
            text_content = biloxy_parse.extract_text_from_pdf(temp_pdf_path)
            if not text_content.strip():
                raise HTTPException(status_code=400, detail="No text extracted from PDF")
            claims_data, pattern_missed_data = biloxy_parse.parse_insurance_claims_with_fallback(text_content, temp_pdf_path)
        
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

        # Create Excel file with both sheets using appropriate parser
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as temp_xlsx:
            temp_xlsx_path = temp_xlsx.name

        if file_type == 'paul':
            paul_parse.create_xlsx_file(claims_data, pattern_missed_data, temp_xlsx_path)
        else:
            biloxy_parse.create_xlsx_file(claims_data, pattern_missed_data, temp_xlsx_path)

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

@app.post("/upload-unpaid/")
async def upload_unpaid_charges(file: UploadFile = File(...)):
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    temp_pdf_path = None
    temp_xlsx_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_pdf:
            content = await file.read()
            temp_pdf.write(content)
            temp_pdf_path = temp_pdf.name

        text_content = unpaid_charges_parse.extract_text_from_pdf(temp_pdf_path)
        if not text_content.strip():
            raise HTTPException(status_code=400, detail="No text extracted from PDF")

        charges_data = unpaid_charges_parse.parse_unpaid_charges(text_content)
        
        if not charges_data:
            raise HTTPException(status_code=400, detail="No unpaid charges data found in PDF")

        base_name = file.filename.rsplit('.', 1)[0]
        output_filename = f"{base_name}_unpaid_charges.xlsx"

        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as temp_xlsx:
            temp_xlsx_path = temp_xlsx.name

        unpaid_charges_parse.create_xlsx_file(charges_data, temp_xlsx_path)

        response = FileResponse(
            temp_xlsx_path,
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            filename=output_filename
        )
        response.headers["Content-Disposition"] = f'attachment; filename="{output_filename}"'
        return response
    
    except Exception as e:
        if temp_pdf_path and os.path.exists(temp_pdf_path):
            os.unlink(temp_pdf_path)
        if temp_xlsx_path and os.path.exists(temp_xlsx_path):
            os.unlink(temp_xlsx_path)
        raise HTTPException(status_code=500, detail=str(e))
    
    finally:
        if temp_pdf_path and os.path.exists(temp_pdf_path):
            os.unlink(temp_pdf_path)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)