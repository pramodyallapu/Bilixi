from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import tempfile
import unpaid_charges_parse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/upload-unpaid/")
async def upload_unpaid_charges(file: UploadFile = File(...)):
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

        # Extract and parse
        text_content = unpaid_charges_parse.extract_text_from_pdf(temp_pdf_path)
        if not text_content.strip():
            raise HTTPException(status_code=400, detail="No text extracted from PDF")

        charges_data = unpaid_charges_parse.parse_unpaid_charges(text_content)
        
        if not charges_data:
            raise HTTPException(status_code=400, detail="No unpaid charges data found in PDF")

        # Generate output filename
        base_name = file.filename.rsplit('.', 1)[0]
        output_filename = f"{base_name}_unpaid_charges.xlsx"

        # Create Excel file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as temp_xlsx:
            temp_xlsx_path = temp_xlsx.name

        unpaid_charges_parse.create_xlsx_file(charges_data, temp_xlsx_path)

        # Return Excel file
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
        # Clean up PDF file
        if temp_pdf_path and os.path.exists(temp_pdf_path):
            os.unlink(temp_pdf_path)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)