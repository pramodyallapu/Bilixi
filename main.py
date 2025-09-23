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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)